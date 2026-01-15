import json
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal
from src.config import current_config

class UIBridge(QObject):
    """
    Acts as the communication bridge between Python and the React Web UI.
    Methods marked with @pyqtSlot are callable from JavaScript.
    Signals defined here can be emitted from Python to trigger JavaScript functions.
    """
    
    # Signals to send data to JS
    # signal_name.emit(json_string)
    status_update = pyqtSignal(str)     # For general system status
    overlay_update = pyqtSignal(str)    # For overlay state {stage, text}
    settings_loaded = pyqtSignal(str)   # To populate settings form

    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance

    @pyqtSlot()
    def request_settings(self):
        """Called by React when it mounts to get initial config."""
        data = {
            "openai_api_key": current_config.openai_api_key,
            "model": current_config.model,
            "system_prompt": current_config.system_prompt,
            "sound_feedback": current_config.sound_feedback,
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
        """Allows the UI to trigger a simulation of the flow."""
        # We can leverage the actual recording logic or a mock
        # For now, let's trigger the real overlay logic with fake data for visual test
        self.app.on_start_recording() 
        # In a real simulation we might just emit signals to the overlay 
        # without actually recording, but this tests the full pipeline.

    @pyqtSlot()
    def close_app(self):
        self.app.quit_app()

    @pyqtSlot()
    def minimize_app(self):
        if self.app.main_window:
            self.app.main_window.showMinimized()
