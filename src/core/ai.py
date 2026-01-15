import os
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
        # We enforce whisper-1 here to prevent 404/400 errors if the user/config
        # has a model string that isn't supported by the audio endpoint (e.g. gpt-4o).
        # We only check if the user provided one is explicitly NOT whisper.
        
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
        
        # Some newer "reasoning" models (like o1, or future gpt-5-nano variants) 
        # do not support the 'temperature' parameter, or require it to be default (1).
        # We try with precision (0.3) first, and fallback if rejected.
        try:
            response = client.chat.completions.create(
                model=current_config.model,
                messages=messages,
                temperature=0.3
            )
        except Exception as e:
            # Check for the specific error about unsupported parameter/value
            err_str = str(e).lower()
            if "temperature" in err_str and ("support" in err_str or "parameter" in err_str):
                print(f"DEBUG: Model '{current_config.model}' rejected temperature param. Retrying with defaults.")
                response = client.chat.completions.create(
                    model=current_config.model,
                    messages=messages
                    # Omit temperature to use model default (usually 1.0)
                )
            else:
                raise e

        return response.choices[0].message.content.strip()
