import json
import os
import time
from typing import List, Dict

HISTORY_FILE = os.path.expanduser("~/.ghostflow_history.json")

class HistoryManager:
    @staticmethod
    def load() -> List[Dict]:
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
            # Ensure it's a list and sort by timestamp desc
            if isinstance(data, list):
                return sorted(data, key=lambda x: x.get('timestamp', 0), reverse=True)
            return []
        except Exception as e:
            print(f"ERROR: Failed to load history: {e}")
            return []

    @staticmethod
    def add(text: str):
        if not text:
            return
        
        history = HistoryManager.load()
        entry = {
            "text": text,
            "timestamp": time.time(),
            "date_str": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Add to top
        history.insert(0, entry)
        
        # Keep last 50
        history = history[:50]
        
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            print(f"ERROR: Failed to save history: {e}")

    @staticmethod
    def clear():
        try:
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
        except Exception as e:
            print(f"ERROR: Failed to clear history: {e}")
