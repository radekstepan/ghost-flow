import json
import os
from dataclasses import dataclass, asdict

CONFIG_FILE = os.path.expanduser("~/.ghostflow_config.json")

@dataclass
class Config:
    openai_api_key: str = ""
    transcription_model: str = "gpt-audio-mini-2025-12-15" 
    model: str = "gpt-5-nano-2025-08-07"
    hotkey: str = "Key.f8"
    sound_feedback: bool = True
    system_prompt: str = (
        "You are a precise dictation assistant. Your task is to correct the grammar, "
        "punctuation, and capitalization of the user's raw transcript. "
        "Remove filler words (um, uh, like). Do not change the meaning. "
        "Do not add introductory text. Output only the refined text."
    )

    def save(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(asdict(self), f, indent=4)
                f.flush()
                os.fsync(f.fileno()) # Ensure write to disk
            print(f"DEBUG: Configuration saved to {CONFIG_FILE}")
        except Exception as e:
            print(f"ERROR: Failed to save config: {e}")

    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                print(f"DEBUG: Loading config from {CONFIG_FILE}")
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                
                # Filter data to only include keys that exist in the Config dataclass
                # and ensure we don't crash on unexpected keys
                valid_keys = Config.__annotations__.keys()
                filtered_data = {k: v for k, v in data.items() if k in valid_keys}
                
                config = Config(**filtered_data)
                
                # Debug print to verify API key load (masked)
                key_status = "Found" if config.openai_api_key else "Empty"
                print(f"DEBUG: Config Loaded. API Key: {key_status}")
                return config
                
            except Exception as e:
                print(f"ERROR: Error loading config (using defaults): {e}")
                return Config()
        else:
            print("DEBUG: No config file found. Using defaults.")
            return Config()

# Global instance
current_config = Config.load()
