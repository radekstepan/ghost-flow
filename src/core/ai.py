import os
import io
import wave
import json
import base64
import numpy as np
from typing import Optional
from scipy.signal import resample_poly
from openai import OpenAI
from websocket import create_connection, WebSocketTimeoutException
from src.config import current_config

REALTIME_SAMPLE_RATE = 24000
REALTIME_BASE_MODEL = "gpt-realtime"

def is_realtime_transcription_model(model_id: Optional[str]) -> bool:
    return "transcribe" in (model_id or "").lower()

def is_whisper_model(model_id: Optional[str]) -> bool:
    return "whisper" in (model_id or "").lower()

def normalize_realtime_transcription_model(model_id: Optional[str]) -> str:
    if not model_id:
        return "gpt-4o-mini-transcribe"

    lowered = model_id.lower()
    if "gpt-4o-mini-transcribe" in lowered:
        return "gpt-4o-mini-transcribe"
    if "gpt-4o-transcribe" in lowered:
        return "gpt-4o-transcribe"
    if "whisper-1" in lowered:
        return "whisper-1"
    return model_id

class AIProcessor:
    def __init__(self):
        # Cached OpenAI client and the API key used to construct it.
        # Tracking the key allows us to recreate the client if the user
        # updates their preferences at runtime.
        self.client = None
        self._client_api_key = None

    def _get_client(self):
        # Ensure an API key exists
        if not current_config.openai_api_key:
            raise ValueError("OpenAI API Key is missing. Please check Preferences.")

        # Recreate the client if it's missing or the API key changed
        if self.client is None or current_config.openai_api_key != self._client_api_key:
            self.client = OpenAI(api_key=current_config.openai_api_key)
            self._client_api_key = current_config.openai_api_key

        return self.client

    def _resample_to_realtime_rate(self, pcm_bytes: bytes, sample_rate: int) -> bytes:
        if sample_rate == REALTIME_SAMPLE_RATE:
            return pcm_bytes
        if not pcm_bytes:
            return b""

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        resampled = resample_poly(audio, REALTIME_SAMPLE_RATE, sample_rate)
        resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
        return resampled.tobytes()

    def _realtime_transcribe_pcm16(self, pcm_bytes: bytes, sample_rate: int, transcription_model: str) -> str:
        if not pcm_bytes:
            return ""

        pcm_24k = self._resample_to_realtime_rate(pcm_bytes, sample_rate)
        audio_b64 = base64.b64encode(pcm_24k).decode("utf-8")

        transcription_model = normalize_realtime_transcription_model(transcription_model)

        url = f"wss://api.openai.com/v1/realtime?model={REALTIME_BASE_MODEL}"
        headers = [
            f"Authorization: Bearer {current_config.openai_api_key}",
            "OpenAI-Beta: realtime=v1",
        ]

        ws = create_connection(url, header=headers)
        ws.settimeout(10)
        completed_transcript = None
        delta_parts = []
        try:
            session_update = {
                "type": "session.update",
                "session": {
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {"model": transcription_model, "language": "en"},
                    "turn_detection": None,
                },
            }
            ws.send(json.dumps(session_update))
            ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64}))
            ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

            while True:
                try:
                    raw = ws.recv()
                except WebSocketTimeoutException:
                    break

                if not raw:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                event = json.loads(raw)
                event_type = event.get("type", "")

                if event_type == "conversation.item.input_audio_transcription.delta":
                    delta = event.get("delta", "")
                    if delta:
                        delta_parts.append(delta)
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    completed_transcript = event.get("transcript", "")
                    break
                elif event_type == "error":
                    err = event.get("error", {})
                    message = err.get("message", "Realtime API error")
                    raise ValueError(message)
        finally:
            ws.close()

        if completed_transcript is not None:
            return completed_transcript.strip()
        return "".join(delta_parts).strip()

    def _read_wav_pcm16(self, audio_path: str) -> tuple[bytes, int]:
        with wave.open(audio_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            pcm_bytes = wf.readframes(wf.getnframes())

        if sample_width != 2:
            raise ValueError("Realtime transcription expects 16-bit PCM WAV input.")

        if channels > 1:
            audio = np.frombuffer(pcm_bytes, dtype=np.int16)
            audio = audio.reshape(-1, channels)[:, 0]
            pcm_bytes = audio.astype(np.int16).tobytes()

        return pcm_bytes, sample_rate

    def transcribe(self, audio_path: str) -> str:
        client = self._get_client()
        
        model_to_use = current_config.transcription_model
        if is_realtime_transcription_model(model_to_use):
            pcm_bytes, sample_rate = self._read_wav_pcm16(audio_path)
            return self._realtime_transcribe_pcm16(pcm_bytes, sample_rate, model_to_use)

        # OpenAI's audio endpoint is strict about model names.
        if not is_whisper_model(model_to_use):
            print(f"DEBUG: Configured model '{model_to_use}' not compatible with audio endpoint. Falling back to 'whisper-1'.")
            model_to_use = "whisper-1"
            
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=model_to_use,
                    file=audio_file,
                    language="en"
                )
            return transcript.text
        except Exception as e:
            print(f"DEBUG: Transcription API error: {e}")
            if "404" in str(e) and "Invalid URL" in str(e):
                raise ValueError("API Endpoint Error: Ensure you are using 'whisper-1' for transcription.")
            raise e

    def refine(self, raw_text: str) -> str:
        client = self._get_client()
        
        messages = [
            {"role": "system", "content": current_config.system_prompt},
            {"role": "user", "content": raw_text}
        ]
        
        # Optimization: Check if this model is known to reject temperature
        # to avoid the roundtrip error.
        use_temp = True
        if current_config.model in current_config.reasoning_models:
            print(f"DEBUG: Model '{current_config.model}' known to not support temperature. Skipping param.")
            use_temp = False

        try:
            kwargs = {
                "model": current_config.model,
                "messages": messages
            }
            if use_temp:
                kwargs["temperature"] = 0.3

            response = client.chat.completions.create(**kwargs)

        except Exception as e:
            err_str = str(e).lower()
            # If we tried to use temperature and failed, record it and retry
            if use_temp and "temperature" in err_str and ("support" in err_str or "parameter" in err_str):
                print(f"DEBUG: Model '{current_config.model}' rejected temperature. Adding to exclusion list and retrying.")
                
                # Update config memory and disk
                if current_config.model not in current_config.reasoning_models:
                    current_config.reasoning_models.append(current_config.model)
                    current_config.save()
                
                # Retry without temperature
                del kwargs["temperature"]
                response = client.chat.completions.create(**kwargs)
            else:
                raise e

        return response.choices[0].message.content.strip()

    def transcribe_pcm16(self, pcm_bytes: bytes, sample_rate: int) -> str:
        """Transcribe raw PCM16 mono bytes using an in-memory WAV buffer."""
        if not pcm_bytes:
            return ""

        model_to_use = current_config.transcription_model
        if is_realtime_transcription_model(model_to_use):
            return self._realtime_transcribe_pcm16(pcm_bytes, sample_rate, model_to_use)

        # Write PCM16 bytes into an in-memory WAV container
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        buf.seek(0)

        client = self._get_client()

        # Ensure a compatible model is selected for audio endpoint
        model_to_use = current_config.transcription_model
        if not is_whisper_model(model_to_use):
            print(f"DEBUG: Configured model '{model_to_use}' not compatible with audio endpoint. Falling back to 'whisper-1'.")
            model_to_use = "whisper-1"

        try:
            transcript = client.audio.transcriptions.create(
                model=model_to_use,
                file=("audio.wav", buf),
                language="en",
            )
            return transcript.text
        except Exception as e:
            print(f"DEBUG: Transcription API error: {e}")
            if "404" in str(e) and "Invalid URL" in str(e):
                raise ValueError("API Endpoint Error: Ensure you are using 'whisper-1' for transcription.")
            raise e
