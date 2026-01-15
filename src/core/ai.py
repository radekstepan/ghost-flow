import os
import tempfile
import numpy as np
import scipy.io.wavfile as wav
from openai import OpenAI
from src.config import current_config

class AIProcessor:
    def __init__(self):
        self.client = None

    def _get_client(self):
        if not current_config.openai_api_key:
            raise ValueError("OpenAI API Key is missing. Please check Preferences.")
        return OpenAI(api_key=current_config.openai_api_key)

    def transcribe(self, audio_path: str) -> str:
        client = self._get_client()
        
        # OpenAI's audio endpoint is strict about model names.
        model_to_use = current_config.transcription_model
        if "whisper" not in model_to_use.lower():
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
        """Transcribe raw PCM16 mono bytes via a temp WAV file."""
        if not pcm_bytes:
            return ""
        audio_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            wav.write(tmp.name, sample_rate, audio_data)
            return self.transcribe(tmp.name)
