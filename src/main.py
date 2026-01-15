import sys
import time
import threading
import pyperclip
import pyautogui
from pynput import keyboard
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QThread

from src.config import current_config
from src.gui.overlay import GhostOverlay
from src.gui.preferences import PreferencesWindow
from src.core.recorder import AudioRecorder
from src.core.ai import AIProcessor

# Worker Thread for AI Processing to keep UI responsive
class TranscriptionWorker(QThread):
    finished = pyqtSignal(str) # Emits cleaned text
    error = pyqtSignal(str)

    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path
        self.processor = AIProcessor()

    def run(self):
        try:
            # 1. Transcribe
            raw_text = self.processor.transcribe(self.audio_path)
            if not raw_text.strip():
                self.error.emit("No speech detected.")
                return

            # 2. Refine
            clean_text = self.processor.refine(raw_text)
            self.finished.emit(clean_text)
        except Exception as e:
            self.error.emit(str(e))

class GhostApp(QObject):
    # Signals to bridge Listener Thread -> Main Qt Thread
    start_rec_signal = pyqtSignal()
    stop_rec_signal = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        
        # Initialize Core Components
        self.recorder = AudioRecorder()
        
        # Initialize GUI
        self.overlay = GhostOverlay()
        self.prefs_window = PreferencesWindow()
        self.setup_tray()

        # Connect Signals
        self.start_rec_signal.connect(self.on_start_recording)
        self.stop_rec_signal.connect(self.on_stop_recording)

        # Start Global Key Listener in a separate thread
        self.listener = keyboard.Listener(
            on_press=self.on_key_press, 
            on_release=self.on_key_release
        )
        self.listener.start()
        
        self.hotkey_pressed = False
        self.processing = False

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # Using a simple system icon or generic file icon for now since we don't have assets
        # In a real app, load from a .png file
        self.tray_icon.setIcon(self.overlay.style().standardIcon(
            self.overlay.style().StandardPixmap.SP_ComputerIcon
        ))
        
        menu = QMenu()
        
        prefs_action = QAction("Preferences", self)
        prefs_action.triggered.connect(self.show_preferences)
        menu.addAction(prefs_action)
        
        quit_action = QAction("Quit Ghost Flow", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def show_preferences(self):
        self.prefs_window.show()
        self.prefs_window.activateWindow()

    def quit_app(self):
        self.listener.stop()
        self.app.quit()

    # --- Key Listener Callbacks (Thread: pynput) ---
    def on_key_press(self, key):
        if self.processing: return
        
        if key == keyboard.Key.f8:
            if not self.hotkey_pressed:
                self.hotkey_pressed = True
                self.start_rec_signal.emit()

    def on_key_release(self, key):
        if key == keyboard.Key.f8:
            if self.hotkey_pressed:
                self.hotkey_pressed = False
                self.stop_rec_signal.emit()

    # --- Main Thread Slots ---
    @pyqtSlot()
    def on_start_recording(self):
        print("Starting recording...")
        self.overlay.set_state("listening")
        try:
            self.recorder.start()
        except Exception as e:
            print(f"Error starting recorder: {e}")

    @pyqtSlot()
    def on_stop_recording(self):
        print("Stopping recording...")
        self.processing = True # Block new inputs
        
        audio_path = self.recorder.stop()
        
        if not audio_path:
            self.overlay.set_state("hidden")
            self.processing = False
            return

        self.overlay.set_state("processing")
        
        # Start Worker Thread
        self.worker = TranscriptionWorker(audio_path)
        self.worker.finished.connect(self.on_ai_success)
        self.worker.error.connect(self.on_ai_error)
        self.worker.start()

    @pyqtSlot(str)
    def on_ai_success(self, text):
        print(f"Injection: {text}")
        self.overlay.set_state("pasting")
        
        # Inject to System
        pyperclip.copy(text)
        # Small delay to ensure clipboard is ready
        QThread.msleep(100) 
        
        # Simulate Paste (Command+V for macOS)
        pyautogui.hotkey('command', 'v')
        
        # Reset UI after short delay
        QTimer.singleShot(1500, self.reset_ui)

    @pyqtSlot(str)
    def on_ai_error(self, msg):
        print(f"Error: {msg}")
        # Could update overlay to show error state here
        self.overlay.set_state("hidden")
        self.processing = False

    def reset_ui(self):
        self.overlay.set_state("hidden")
        self.processing = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep running for tray icon
    
    ghost_flow = GhostApp(app)
    
    sys.exit(app.exec())
