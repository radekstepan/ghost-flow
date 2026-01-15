import json
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer
from src.config import current_config

class UIBridge(QObject):
    """
    Acts as the communication bridge between Python and the React Web UI.
    Methods marked with @pyqtSlot are callable from JavaScript.
    Signals defined here can be emitted from Python to trigger JavaScript functions.
    """
    
    # Signals to send data to JS
    status_update = pyqtSignal(str)     # For general system status
    overlay_update = pyqtSignal(str)    # For overlay state {stage, text}
    settings_loaded = pyqtSignal(str)   # To populate settings form

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.last_overlay_state = json.dumps({"stage": "idle", "text": ""})

    def emit_overlay_update(self, data: str):
        """Store and emit overlay updates so late subscribers can sync."""
        print(f"DEBUG: Bridge emitting overlay_update: {data}")
        self.last_overlay_state = data
        self.overlay_update.emit(data)
        print("DEBUG: Bridge overlay_update.emit() called")

    @pyqtSlot(result=str)
    def get_overlay_state(self):
        """Return latest overlay state for late-connecting UIs."""
        return self.last_overlay_state

    @pyqtSlot()
    def request_settings(self):
        """Called by React when it mounts to get initial config."""
        perms = getattr(self.app, 'permissions_granted', True)
        print(f"DEBUG: Bridge sending permissions_granted: {perms}")
        
        data = {
            "openai_api_key": current_config.openai_api_key,
            "model": current_config.model,
            "system_prompt": current_config.system_prompt,
            "sound_feedback": current_config.sound_feedback,
            "permissions_granted": perms
        }
        self.settings_loaded.emit(json.dumps(data))

    @pyqtSlot(str)
    def save_settings(self, json_str):
        """Called by React to save config."""
        try:
            data = json.loads(json_str)
            current_config.openai_api_key = data.get("openai_api_key", "")
            current_config.model = data.get("model", "gpt-4o-mini")
            current_config.system_prompt = data.get("system_prompt", "")
            current_config.sound_feedback = data.get("sound_feedback", True)
            current_config.save()
            print("Settings saved via Bridge")
        except Exception as e:
            print(f"Error saving settings: {e}")

    @pyqtSlot()
    def simulate_recording(self):
        """Triggers a 3-second recording simulation."""
        print("DEBUG: Simulation started via Bridge")
        self.app.on_start_recording()
        
        # Automatically stop after 3 seconds to complete the cycle
        QTimer.singleShot(3000, self.app.on_stop_recording)

    @pyqtSlot()
    def close_app(self):
        self.app.quit_app()

    @pyqtSlot()
    def minimize_app(self):
        if self.app.main_window:
            self.app.main_window.showMinimized()
