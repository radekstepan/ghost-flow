import sys
import json
import time
import queue
import pyautogui
import pyperclip
import ctypes
import subprocess
from ctypes import util
from pynput import keyboard
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QBrush, QRadialGradient, QPen
from PyQt6.QtCore import pyqtSlot, QThread, QTimer, Qt, QObject, pyqtSignal, QSize

from src.config import current_config
from src.core.recorder import AudioRecorder
from src.core.ai import AIProcessor
from src.core.history import HistoryManager

# New GUI components
from src.gui.bridge import UIBridge
from src.gui.web_window import WebWindow

try:
    import webrtcvad
except Exception as e:
    print(f"WARNING: Failed to import webrtcvad: {e}")
    webrtcvad = None

class TranscriptionWorker(QThread):
    finished = pyqtSignal(str) 
    error = pyqtSignal(str)

    def __init__(self, audio_path):
        super().__init__()
        self.audio_path = audio_path
        self.processor = AIProcessor()

    def run(self):
        print("DEBUG: TranscriptionWorker started")
        try:
            if not current_config.openai_api_key:
                raise ValueError("No OpenAI API Key set.")

            raw_text = self.processor.transcribe(self.audio_path)
            print(f"DEBUG: Raw Transcribe Result: '{raw_text}'")
            
            if not raw_text or not raw_text.strip():
                self.error.emit("No speech detected.")
                return
            
            clean_text = self.processor.refine(raw_text)
            print(f"DEBUG: Refined Text: '{clean_text}'")
            self.finished.emit(clean_text)
        except Exception as e:
            print(f"DEBUG: TranscriptionWorker Error: {e}")
            self.error.emit(str(e))

class StreamingTranscriptionWorker(QThread):
    partial_update = pyqtSignal(str, str)   # finalized_text, live_text
    session_finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, frame_queue, sample_rate, vad_silence_ms=600, vad_aggressiveness=2, min_segment_ms=300):
        super().__init__()
        self.frame_queue = frame_queue
        self.sample_rate = sample_rate
        self.vad_silence_ms = vad_silence_ms
        self.vad_aggressiveness = vad_aggressiveness
        self.min_segment_ms = min_segment_ms
        self._stop_requested = False
        self._error_emitted = False
        self.processor = AIProcessor()
        self._finalized_segments = []

    def request_stop(self):
        self._stop_requested = True

    def _finalized_text(self):
        parts = [p.strip() for p in self._finalized_segments if p and p.strip()]
        return " ".join(parts).strip()

    def _frame_bytes(self, frame):
        if hasattr(frame, "ndim") and frame.ndim > 1:
            frame = frame[:, 0]
        return frame.tobytes()

    def _process_segment(self, frames_bytes, segment_ms):
        if segment_ms < self.min_segment_ms:
            return
        pcm_bytes = b"".join(frames_bytes)
        try:
            text = self.processor.transcribe_pcm16(pcm_bytes, self.sample_rate)
        except Exception as e:
            self._error_emitted = True
            self.error.emit(str(e))
            return
        if text and text.strip():
            try:
                refined = self.processor.refine(text.strip())
            except Exception as e:
                self._error_emitted = True
                self.error.emit(str(e))
                return
            self._finalized_segments.append(refined.strip())
            self.partial_update.emit(self._finalized_text(), refined.strip())

    def run(self):
        print("DEBUG: StreamingTranscriptionWorker started")
        if webrtcvad is None:
            self.error.emit("Streaming VAD not available.")
            return

        try:
            vad = webrtcvad.Vad(self.vad_aggressiveness)
        except Exception as e:
            self.error.emit(str(e))
            return

        silence_ms = 0
        current_frames = []
        current_duration = 0
        frame_ms = None
        in_speech = False

        while True:
            if self._stop_requested and self.frame_queue.empty():
                break
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if frame is None:
                continue
            if frame_ms is None:
                frame_ms = int(1000 * frame.shape[0] / self.sample_rate)

            frame_bytes = self._frame_bytes(frame)
            is_speech = vad.is_speech(frame_bytes, self.sample_rate)

            if is_speech:
                if not in_speech:
                    print("DEBUG: VAD speech start")
                    in_speech = True
                current_frames.append(frame_bytes)
                current_duration += frame_ms
                silence_ms = 0
            else:
                if current_frames:
                    silence_ms += frame_ms
                    if silence_ms >= self.vad_silence_ms:
                        print(f"DEBUG: VAD silence reached ({silence_ms}ms). Closing segment ({current_duration}ms).")
                        self._process_segment(current_frames, current_duration)
                        if self._error_emitted:
                            return
                        current_frames = []
                        current_duration = 0
                        silence_ms = 0
                        in_speech = False

        if current_frames:
            self._process_segment(current_frames, current_duration)
            if self._error_emitted:
                return

        final_text = self._finalized_text()
        if final_text and final_text.strip():
            try:
                final_text = self.processor.refine(final_text.strip())
            except Exception as e:
                self._error_emitted = True
                self.error.emit(str(e))
                return

        self.session_finished.emit(final_text)

class GhostApp(QObject):
    start_rec_signal = pyqtSignal()
    stop_rec_signal = pyqtSignal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        
        # Check macOS Accessibility Permissions explicitly
        self.permissions_granted = self.check_permissions()
        print(f"DEBUG: Accessibility Permissions Granted: {self.permissions_granted}")
        
        # Core
        self.recorder = AudioRecorder()
        self.processing = False
        self.streaming_worker = None
        self.streaming_queue = None
        self.streaming_stop_requested = False
        
        # State for Hybrid Trigger (Hold for PTT, Tap for Toggle)
        self.recording_start_time = 0.0
        self.recording_mode = None # None, 'evaluating', 'toggle'
        
        # Bridge & Windows
        self.bridge = UIBridge(self)
        
        # 1. Main Preferences Window
        self.main_window = WebWindow(self.bridge, mode="settings", width=960, height=640)
        self.main_window.show()
        
        # 2. Overlay Window (Hidden initially)
        # Reduced height for a tighter fit
        self.overlay_window = WebWindow(self.bridge, mode="overlay", width=340, height=80)
        
        # Initial positioning
        self.reposition_overlay()
        
        # System Tray
        self.setup_tray()

        # Connect Signals
        self.start_rec_signal.connect(self.on_start_recording)
        self.stop_rec_signal.connect(self.on_stop_recording)

        # Keyboard Listener
        self.listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        self.listener.start()
        self.hotkey_pressed = False

    def check_permissions(self):
        """Checks if the process is trusted by macOS Accessibility."""
        if sys.platform != 'darwin':
            return True
        try:
            # Try to load ApplicationServices
            path = util.find_library('ApplicationServices')
            if not path:
                path = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
            
            lib = ctypes.cdll.LoadLibrary(path)
            
            # AXIsProcessTrusted returns a boolean (true/false)
            lib.AXIsProcessTrusted.argtypes = []
            lib.AXIsProcessTrusted.restype = ctypes.c_bool
            
            is_trusted = lib.AXIsProcessTrusted()
            return is_trusted

        except Exception as e:
            print(f"Warning: Could not check accessibility permissions: {e}")
            return False

    def create_tray_icon(self):
        """Programmatically draws the Ghost Flow icon (Purple Waveform) at high res."""
        # Use 128x128 for Retina sharpness
        size = 128
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background circle for contrast
        circle_size = 126
        circle_x = (size - circle_size) // 2
        circle_y = (size - circle_size) // 2
        gradient = QRadialGradient(size / 2, size / 2, circle_size / 2)
        gradient.setColorAt(0.0, QColor(24, 24, 38))   # Deep slate
        gradient.setColorAt(0.7, QColor(12, 12, 20))   # Darker edge
        gradient.setColorAt(1.0, QColor(5, 5, 10))     # Outer ring
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(circle_x, circle_y, circle_size, circle_size)

        # Thin ring for separation from tray background
        ring_pen = QPen(QColor(255, 255, 255, 40))
        ring_pen.setWidth(2)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(circle_x, circle_y, circle_size, circle_size)
        
        # Colors (Gradient-like steps)
        # Indigo -> Purple -> Fuchsia
        c1 = QColor(99, 102, 241)   # Indigo-500
        c2 = QColor(168, 85, 247)   # Purple-500
        c3 = QColor(236, 72, 153)   # Pink-500

        # Soft glow behind bars
        glow = QColor(99, 102, 241, 90)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Dimensions calculations
        # 3 bars, 20px wide, 14px gap. Total width = 60 + 28 = 88.
        # Center X = 64. Start X = 64 - 44 = 20.
        bar_w = 20
        gap = 12
        radius = 9
        start_x = (size - (bar_w * 3 + gap * 2)) // 2
        
        # 1. Left Bar (Small)
        h1 = 48
        y1 = (size - h1) // 2
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(start_x - 1, y1 - 2, bar_w + 2, h1 + 4, radius + 2, radius + 2)
        painter.setBrush(QBrush(c1))
        painter.drawRoundedRect(start_x, y1, bar_w, h1, radius, radius)
        
        # 2. Center Bar (Tall)
        h2 = 88
        y2 = (size - h2) // 2
        x2 = start_x + bar_w + gap
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(x2 - 1, y2 - 2, bar_w + 2, h2 + 4, radius + 2, radius + 2)
        painter.setBrush(QBrush(c2))
        painter.drawRoundedRect(x2, y2, bar_w, h2, radius, radius)
        
        # 3. Right Bar (Medium)
        h3 = 64
        y3 = (size - h3) // 2
        x3 = x2 + bar_w + gap
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(x3 - 1, y3 - 2, bar_w + 2, h3 + 4, radius + 2, radius + 2)
        painter.setBrush(QBrush(c3))
        painter.drawRoundedRect(x3, y3, bar_w, h3, radius, radius)
        
        painter.end()
        return QIcon(pixmap)

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.create_tray_icon())
        
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
        if self.listener:
            self.listener.stop()
        self.app.quit()
        
    def reposition_overlay(self):
        """Calculates overlay position based on config."""
        pos = current_config.overlay_position
        screen_geo = self.main_window.screen().availableGeometry()
        
        # Margins
        mx = 24
        my = 40 # Top bar allowance
        
        w = self.overlay_window.width()
        h = self.overlay_window.height()
        
        x, y = 0, 0
        
        if pos == "top-right":
            x = screen_geo.x() + screen_geo.width() - w - mx
            y = screen_geo.y() + my
        elif pos == "top-left":
            x = screen_geo.x() + mx
            y = screen_geo.y() + my
        elif pos == "bottom-right":
            x = screen_geo.x() + screen_geo.width() - w - mx
            y = screen_geo.y() + screen_geo.height() - h - mx
        elif pos == "bottom-left":
            x = screen_geo.x() + mx
            y = screen_geo.y() + screen_geo.height() - h - mx
        elif pos == "center":
            x = screen_geo.x() + (screen_geo.width() - w) // 2
            y = screen_geo.y() + (screen_geo.height() - h) // 2
        elif pos == "top-center":
            x = screen_geo.x() + (screen_geo.width() - w) // 2
            y = screen_geo.y() + my
        elif pos == "bottom-center":
            x = screen_geo.x() + (screen_geo.width() - w) // 2
            y = screen_geo.y() + screen_geo.height() - h - mx
        else:
            # Default top-right
            x = screen_geo.x() + screen_geo.width() - w - mx
            y = screen_geo.y() + my
            
        self.overlay_window.move(int(x), int(y))

    def play_sound(self, sound_name):
        """Plays a system sound on macOS using afplay (non-blocking)."""
        if not current_config.sound_feedback:
            return
        
        # Map nice abstract names to actual macOS system sounds
        sound_map = {
            "start": "/System/Library/Sounds/Tink.aiff",
            "stop": "/System/Library/Sounds/Pop.aiff",
            "error": "/System/Library/Sounds/Basso.aiff",
            "success": "/System/Library/Sounds/Glass.aiff"
        }
        
        path = sound_map.get(sound_name)
        if path:
            try:
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"DEBUG: Failed to play sound {sound_name}: {e}")

    def get_configured_key(self):
        """Resolves the configured hotkey string to a pynput Key object."""
        k = current_config.hotkey
        try:
            if k.startswith("Key."):
                attr = k.split(".")[1]
                return getattr(keyboard.Key, attr, keyboard.Key.f8)
            # Handle single characters (e.g. 'r')
            if len(k) == 1:
                return keyboard.KeyCode.from_char(k)
        except Exception:
            pass
        return keyboard.Key.f8

    # --- Interaction ---
    def on_key_press(self, key):
        if self.processing: return
        
        target_key = self.get_configured_key()
        if key == target_key:
            if not self.hotkey_pressed:
                self.hotkey_pressed = True
                
                # Hybrid Trigger Logic
                if self.recording_mode == 'toggle':
                    # User tapped again to stop
                    self.stop_rec_signal.emit()
                    self.recording_mode = None
                elif self.recording_mode is None:
                    # Initial press -> Start
                    self.recording_start_time = time.time()
                    self.recording_mode = 'evaluating'
                    self.start_rec_signal.emit()

    def on_key_release(self, key):
        target_key = self.get_configured_key()
        if key == target_key:
            self.hotkey_pressed = False
            
            if self.recording_mode == 'evaluating':
                # Check how long it was held
                duration = time.time() - self.recording_start_time
                if duration < 0.4: # 400ms threshold for Tap vs Hold
                    print("DEBUG: Tap detected (<0.4s). Switching to TOGGLE mode.")
                    self.recording_mode = 'toggle'
                    # Do NOT stop recording; stay latched
                else:
                    print("DEBUG: Hold detected (>0.4s). Stopping (PTT).")
                    self.stop_rec_signal.emit()
                    self.recording_mode = None

    # --- Logic ---
    @pyqtSlot()
    def on_start_recording(self):
        if self.processing: return
        # Prevent double-start if already recording
        if self.recorder.is_recording: return
        
        print("DEBUG: Starting recording...")
        self.play_sound("start")
        
        # Ensure position is correct (in case config changed)
        self.reposition_overlay()
        
        # Show Overlay using specialized method to prevent focus stealing
        self.overlay_window.show_overlay()
        
        self._update_overlay("listening", "")
        
        use_streaming = current_config.streaming_enabled
        print(f"DEBUG: Streaming enabled={use_streaming}, vad_silence_ms={current_config.vad_silence_ms}, vad_aggressiveness={current_config.vad_aggressiveness}, webrtcvad_available={webrtcvad is not None}")
        if use_streaming and webrtcvad is None:
            print("WARNING: webrtcvad not available. Falling back to batch mode.")
            use_streaming = False

        try:
            if use_streaming:
                print("DEBUG: Starting in streaming mode")
                self.streaming_stop_requested = False
                self.streaming_queue = queue.Queue(maxsize=200)
                self.streaming_worker = StreamingTranscriptionWorker(
                    self.streaming_queue,
                    self.recorder.sample_rate,
                    vad_silence_ms=current_config.vad_silence_ms,
                    vad_aggressiveness=current_config.vad_aggressiveness
                )
                self.streaming_worker.partial_update.connect(self.on_stream_partial)
                self.streaming_worker.session_finished.connect(self.on_stream_final)
                self.streaming_worker.error.connect(self.on_stream_error)
                self.streaming_worker.start()
                self.recorder.start_streaming(self.streaming_queue)
            else:
                print("DEBUG: Starting in batch mode")
                self.recorder.start()
        except Exception as e:
            print(f"Recorder Error: {e}")
            self._update_overlay("done", "Mic Error")

    @pyqtSlot()
    def on_stop_recording(self):
        # Prevent stopping if not recording
        if not self.recorder.is_recording: return

        print("DEBUG: Stopping recording...")
        self.play_sound("stop")
        self.processing = True
        
        if self.recorder.streaming:
            try:
                self.processing = True
                self.streaming_stop_requested = True
                self.recorder.stop_streaming()
                if self.streaming_worker:
                    self.streaming_worker.request_stop()
                self._update_overlay("idle", "")
            except Exception as e:
                print(f"Recorder Stop Error: {e}")
                self.reset_ui()
            return

        try:
            audio_path = self.recorder.stop()
        except Exception as e:
            print(f"Recorder Stop Error: {e}")
            self.reset_ui()
            return
        
        if not audio_path:
            print("DEBUG: No audio recorded (silent or empty).")
            self._update_overlay("done", "No Audio")
            QTimer.singleShot(1500, self.reset_ui)
            return

        self._update_overlay("processing", "")
        
        self.worker = TranscriptionWorker(audio_path)
        self.worker.finished.connect(self.on_ai_success)
        self.worker.error.connect(self.on_ai_error)
        self.worker.start()

    @pyqtSlot(str)
    def on_ai_success(self, text):
        print(f"DEBUG: Success Result: {text}")
        
        # Save to History
        HistoryManager.add(text)
        
        self._update_overlay("done", text)
        
        # Copy & Paste
        pyperclip.copy(text)
        QThread.msleep(100)
        # Use a timer to paste so we don't block
        QTimer.singleShot(100, lambda: pyautogui.hotkey('command', 'v'))
        
        # Hide after 2 seconds
        QTimer.singleShot(2500, self.reset_ui)

    @pyqtSlot(str)
    def on_ai_error(self, msg):
        print(f"DEBUG: AI Error Signal Received: {msg}")
        self.play_sound("error")
        # Strip generic python error text to keep overlay clean if possible
        display_msg = "Error"
        if "API Key" in msg:
            display_msg = "No API Key"
        elif "No speech" in msg:
            display_msg = "No Speech"
            
        self._update_overlay("done", display_msg)
        QTimer.singleShot(2000, self.reset_ui)

    @pyqtSlot(str, str)
    def on_stream_partial(self, finalized_text, live_text):
        if self.streaming_stop_requested:
            return
        payload_text = live_text or ""
        if payload_text:
            self._update_overlay("listening", payload_text, finalized=finalized_text, live=live_text)
            paste_text = payload_text.strip()
            if paste_text:
                if not paste_text.endswith((" ", "\n", "\t")):
                    paste_text += " "
                pyperclip.copy(paste_text)
                QTimer.singleShot(0, lambda: pyautogui.hotkey('command', 'v'))

    @pyqtSlot(str)
    def on_stream_final(self, final_text):
        if not final_text or not final_text.strip():
            self._update_overlay("done", "No Audio")
            QTimer.singleShot(1500, self.reset_ui)
            return

        HistoryManager.add(final_text)
        self._update_overlay("done", final_text)

        pyperclip.copy(final_text)
        QTimer.singleShot(2500, self.reset_ui)

    @pyqtSlot(str)
    def on_stream_error(self, msg):
        print(f"DEBUG: Streaming Error Signal Received: {msg}")
        if self.recorder.is_recording and self.recorder.streaming:
            try:
                self.recorder.stop_streaming()
            except Exception:
                pass
        self.play_sound("error")
        display_msg = "Error"
        if "API Key" in msg:
            display_msg = "No API Key"
        elif "No speech" in msg:
            display_msg = "No Speech"
        self._update_overlay("done", display_msg)
        QTimer.singleShot(2000, self.reset_ui)

    def reset_ui(self):
        self.overlay_window.hide()
        self._update_overlay("idle", "")
        self.processing = False
        self.streaming_worker = None
        self.streaming_queue = None
        self.streaming_stop_requested = False
        # Note: self.recording_mode is managed by key listener thread to avoid races.

    def _update_overlay(self, stage, text, **extra):
        print(f"DEBUG: _update_overlay called with stage={stage}, text={text}")
        payload = {"stage": stage, "text": text}
        payload.update(extra)
        data = json.dumps(payload)
        self.bridge.emit_overlay_update(data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    ghost = GhostApp(app)
    
    sys.exit(app.exec())
