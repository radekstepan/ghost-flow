from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QBrush, QFont

class GhostOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Dimensions and Positioning
        self.resize(300, 80)
        self._center_on_screen()

        # Layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(20, 10, 20, 10)

        # Status Icon/Animation Container
        self.icon_area = QLabel()
        self.icon_area.setFixedSize(20, 20)
        self.icon_area.setStyleSheet("background-color: #6366f1; border-radius: 10px;")
        
        # Text Label
        self.label = QLabel("LISTENING...")
        self.label.setFont(QFont("SF Pro Display", 14, QFont.Weight.Bold))
        self.label.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout.addWidget(self.icon_area)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.label)
        self.layout.addStretch()

        # Animation Timer for "Thinking"
        self.timer = QTimer()
        self.timer.timeout.connect(self._animate_thinking)
        self.pulse_phase = 0

    def _center_on_screen(self):
        screen = self.screen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) - 200 # Bottom center-ish
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Glassmorphism Background
        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Dark semi-transparent background (Neutral-900 with alpha)
        brush = QBrush(QColor(23, 23, 23, 230))
        painter.setBrush(brush)
        painter.drawRoundedRect(rect, 40, 40)
        
        # Subtle Border
        pen = painter.pen()
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setColor(QColor(255, 255, 255, 30))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(rect.adjusted(1,1,-1,-1), 40, 40)

    def set_state(self, state: str):
        self.show()
        if state == "listening":
            self.label.setText("LISTENING...")
            self.icon_area.setStyleSheet("background-color: #ef4444; border-radius: 10px;") # Red pulse
            self.timer.stop()
        elif state == "processing":
            self.label.setText("REFINING...")
            self.timer.start(100)
        elif state == "pasting":
            self.label.setText("PASTING")
            self.icon_area.setStyleSheet("background-color: #22c55e; border-radius: 10px;") # Green check
            self.timer.stop()
        elif state == "hidden":
            self.timer.stop()
            self.hide()

    def _animate_thinking(self):
        # Simple pulsing effect for the icon during processing
        colors = ["#6366f1", "#818cf8", "#a5b4fc", "#c7d2fe"]
        self.pulse_phase = (self.pulse_phase + 1) % len(colors)
        self.icon_area.setStyleSheet(f"background-color: {colors[self.pulse_phase]}; border-radius: 10px;")
