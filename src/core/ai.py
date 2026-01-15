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
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en"
            )
        return transcript.text

    def refine(self, raw_text: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=current_config.model,
            messages=[
                {"role": "system", "content": current_config.system_prompt},
                {"role": "user", "content": raw_text}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
