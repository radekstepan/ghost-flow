from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
    QCheckBox, QFormLayout, QTextEdit, QComboBox
)
from PyQt6.QtCore import Qt
from src.config import current_config

class PreferencesWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ghost Flow Preferences")
        self.resize(500, 400)
        self.setStyleSheet("""
            QWidget { background-color: #171717; color: #f3f4f6; font-family: sans-serif; }
            QLineEdit, QTextEdit, QComboBox { 
                background-color: #262626; border: 1px solid #404040; 
                border-radius: 6px; padding: 8px; color: white; selection-background-color: #6366f1;
            }
            QPushButton {
                background-color: #6366f1; color: white; border: none;
                border-radius: 6px; padding: 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4f46e5; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Header
        header = QLabel("Settings")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #6366f1;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(15)

        # API Key
        self.api_key_input = QLineEdit(current_config.openai_api_key)
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("OpenAI API Key:", self.api_key_input)

        # Model Selection
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gpt-4o-mini", "gpt-4o"])
        self.model_combo.setCurrentText(current_config.model)
        form.addRow("Model:", self.model_combo)

        # System Prompt
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(current_config.system_prompt)
        self.prompt_edit.setFixedHeight(100)
        form.addRow("System Prompt:", self.prompt_edit)

        layout.addLayout(form)

        # Buttons
        save_btn = QPushButton("Save Configuration")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()

    def save_settings(self):
        current_config.openai_api_key = self.api_key_input.text().strip()
        current_config.model = self.model_combo.currentText()
        current_config.system_prompt = self.prompt_edit.toPlainText()
        current_config.save()
        self.close()
