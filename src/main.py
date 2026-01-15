import sys
import json
import pyautogui
import pyperclip
from pynput import keyboard
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import pyqtSlot, QThread, QTimer, Qt, QObject, pyqtSignal

from src.config import current_config
from src.core.recorder import AudioRecorder
from src.core.ai import AIProcessor

# New GUI components
from src.gui.bridge import UIBridge
from src.gui.web_window import WebWindow

class TranscriptionWorker(QThread):
    finished = pyqtSignal(str) 
    error = pyqtSignal(str)

    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path
        self.processor = AIProcessor()

    def run(self):
        try:
            raw_text = self.processor.transcribe(self.audio_path)
            if not raw_text.strip():
                self.error.emit("No speech detected.")
                return
            clean_text = self.processor.refine(raw_text)
            self.finished.emit(clean_text)
        except Exception as e:
            self.error.emit(str(e))

class GhostApp(QObject):
    start_rec_signal = pyqtSignal()
    stop_rec_signal = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        
        # Core
        self.recorder = AudioRecorder()
        self.processing = False
        
        # Bridge & Windows
        self.bridge = UIBridge(self)
        
        # 1. Main Preferences Window
        self.main_window = WebWindow(self.bridge, mode="settings", width=960, height=640)
        self.main_window.show()
        
        # 2. Overlay Window (Hidden initially)
        self.overlay_window = WebWindow(self.bridge, mode="overlay", width=400, height=200)
        # Center the overlay manually (roughly)
        screen = self.main_window.screen().geometry()
        ox = (screen.width() - 400) // 2
        oy = (screen.height() // 2) - 200
        self.overlay_window.move(ox, oy)
        
        # System Tray
        self.setup_tray()

        # Connect Signals
        self.start_rec_signal.connect(self.on_start_recording)
        self.stop_rec_signal.connect(self.on_stop_recording)

        # Keyboard Listener
        self.listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.listener.start()
        self.hotkey_pressed = False

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon.fromTheme("audio-input-microphone"))
        
        menu = QMenu()
        show_action = QAction("Show Settings", self)
        show_action.triggered.connect(lambda: self.main_window.show())
        menu.addAction(show_action)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def quit_app(self):
        self.listener.stop()
        self.app.quit()

    # --- Interaction ---
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

    # --- Logic ---
    @pyqtSlot()
    def on_start_recording(self):
        if self.processing: return
        print("Starting recording...")
        
        # Show Overlay
        self.overlay_window.show()
        self._update_overlay("listening", "")
        
        try:
            if current_config.sound_feedback:
                # Play sound here if implemented
                pass
            self.recorder.start()
        except Exception as e:
            print(f"Recorder Error: {e}")

    @pyqtSlot()
    def on_stop_recording(self):
        print("Stopping recording...")
        self.processing = True
        audio_path = self.recorder.stop()
        
        if not audio_path:
            self.reset_ui()
            return

        self._update_overlay("processing", "")
        
        self.worker = TranscriptionWorker(audio_path)
        self.worker.finished.connect(self.on_ai_success)
        self.worker.error.connect(self.on_ai_error)
        self.worker.start()

    @pyqtSlot(str)
    def on_ai_success(self, text):
        print(f"Result: {text}")
        self._update_overlay("done", text)
        
        # Copy & Paste
        pyperclip.copy(text)
        QThread.msleep(100)
        # Use a timer to paste so we don't block
        QTimer.singleShot(100, lambda: pyautogui.hotkey('command', 'v'))
        
        # Hide after 2 seconds
        QTimer.singleShot(2000, self.reset_ui)

    @pyqtSlot(str)
    def on_ai_error(self, msg):
        print(f"AI Error: {msg}")
        self._update_overlay("done", "Error") # Or error state
        QTimer.singleShot(1500, self.reset_ui)

    def reset_ui(self):
        self.overlay_window.hide()
        self._update_overlay("idle", "")
        self.processing = False

    def _update_overlay(self, stage, text):
        data = json.dumps({"stage": stage, "text": text})
        self.bridge.overlay_update.emit(data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    ghost = GhostApp(app)
    
    sys.exit(app.exec())
