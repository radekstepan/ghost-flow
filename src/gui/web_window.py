import os
import sys
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, Qt, QTimer

# Custom Page to intercept Console Logs (Crucial for debugging blank screens)
class WebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Forward JS console logs to Python stdout
        print(f"JS [{lineNumber}]: {message}")

class WebWindow(QMainWindow):
    def __init__(self, bridge, mode="settings", width=900, height=600):
        super().__init__()
        self.bridge = bridge
        self.mode = mode
        
        # Window Setup
        self.resize(width, height)
        self.setWindowTitle("Ghost Flow")
        
        # Transparent background setup
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        if mode == "overlay":
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint | 
                Qt.WindowType.Tool
            )
        else:
            # Main settings window
            pass 

        # Web Engine Setup
        self.webview = QWebEngineView(self)
        
        # Use our custom page that captures logs
        self.page = WebPage(self.webview)
        self.webview.setPage(self.page)
        
        # Transparency settings
        self.webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.page.setBackgroundColor(Qt.GlobalColor.transparent)
        
        # Developer settings (optional, helps with debugging)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        # Setup Bridge Channel
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.page.setWebChannel(self.channel)

        # Load Content
        # We assume web_window.py is in src/gui/
        # and app.html is in src/ui/
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../ui/app.html"))
        
        if not os.path.exists(html_path):
            print(f"ERROR: HTML file not found at {html_path}")
        else:
            print(f"Loading HTML: {html_path}")

        url = QUrl.fromLocalFile(html_path)
        # We use a fragment to tell the React app which view to render (#settings or #overlay)
        url.setFragment(mode) 
        self.webview.load(url)
        
        self.setCentralWidget(self.webview)
