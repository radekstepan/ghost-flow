import json
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer
from src.config import current_config, Config
from src.core.history import HistoryManager

class UIBridge(QObject):
    """
    Acts as the communication bridge between Python and the React Web UI.
    """
    
    # Signals to send data to JS
    status_update = pyqtSignal(str)     # For general system status
    overlay_update = pyqtSignal(str)    # For overlay state {stage, text}
    
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.last_overlay_state = json.dumps({"stage": "idle", "text": ""})

    def emit_overlay_update(self, data: str):
        """Store and emit overlay updates so late subscribers can sync."""
        self.last_overlay_state = data
        self.overlay_update.emit(data)

    @pyqtSlot(result=str)
    def get_overlay_state(self):
        """Return latest overlay state for late-connecting UIs."""
        return self.last_overlay_state

    @pyqtSlot(result=str)
    def get_settings(self):
        """Called by React to fetch config synchronously (via callback)."""
        perms = getattr(self.app, 'permissions_granted', True)
        print("DEBUG: Bridge get_settings called")
        
        data = {
            "openai_api_key": current_config.openai_api_key,
            "transcription_model": current_config.transcription_model,
            "model": current_config.model,
            "system_prompt": current_config.system_prompt,
            "sound_feedback": current_config.sound_feedback,
            "permissions_granted": perms
        }
        return json.dumps(data)

    @pyqtSlot(str)
    def save_settings(self, json_str):
        """Called by React to save config."""
        try:
            data = json.loads(json_str)
            
            # Dynamic update based on Config fields
            valid_keys = Config.__annotations__.keys()
            changed = False
            
            for key in valid_keys:
                if key in data:
                    current_value = getattr(current_config, key)
                    new_value = data[key]
                    if current_value != new_value:
                        setattr(current_config, key, new_value)
                        changed = True
            
            if changed:
                current_config.save()
                print("DEBUG: Settings saved via Bridge")
                
        except Exception as e:
            print(f"ERROR: Error saving settings in Bridge: {e}")

    @pyqtSlot(result=str)
    def get_history(self):
        """Returns the history list as a JSON string."""
        return json.dumps(HistoryManager.load())

    @pyqtSlot()
    def clear_history(self):
        """Clears the history file."""
        HistoryManager.clear()
        print("DEBUG: History cleared via Bridge")

    @pyqtSlot()
    def simulate_recording(self):
        """Triggers a 3-second recording simulation."""
        print("DEBUG: Simulation started via Bridge")
        self.app.on_start_recording()
        QTimer.singleShot(3000, self.app.on_stop_recording)

    @pyqtSlot()
    def close_app(self):
        self.app.quit_app()

    @pyqtSlot()
    def minimize_app(self):
        if self.app.main_window:
            self.app.main_window.showMinimized()
