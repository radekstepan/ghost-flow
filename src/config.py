import json
import os
from dataclasses import dataclass

CONFIG_FILE = os.path.expanduser("~/.ghostflow_config.json")

@dataclass
class Config:
    openai_api_key: str = ""
    model: str = "gpt-4o-mini"
    hotkey: str = "Key.f8"
    sound_feedback: bool = True
    system_prompt: str = (
        "You are a precise dictation assistant. Your task is to correct the grammar, "
        "punctuation, and capitalization of the user's raw transcript. "
        "Remove filler words (um, uh, like). Do not change the meaning. "
        "Do not add introductory text. Output only the refined text."
    )

    def save(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.__dict__, f, indent=4)

    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    return Config(**data)
            except Exception:
                return Config()
        return Config()

# Global instance
current_config = Config.load()
