from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QTextBrowser
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class AboutDialog(QDialog):
    """About dialog showing app information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About MP3 Player Genie")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("MP3 Player Genie")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Version
        version = QLabel("Version 2.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        
        # Description
        description = QTextBrowser()
        description.setOpenExternalLinks(True)
        description.setHtml("""
            <p>MP3 Player Genie is designed to help parents manage music for their children's portable media players. 
            In an age where streaming and social media dominate, this tool enables offline music enjoyment without 
            constant internet connectivity.</p>
            
            <h3>Key Features:</h3>
            <ul>
                <li>Download music from public domain sources</li>
                <li>Automatic metadata tagging and organization</li>
                <li>Content filtering for family-friendly music</li>
                <li>Direct transfer to portable media players</li>
                <li>Works offline once music is downloaded</li>
            </ul>
            
            <h3>Why MP3 Player Genie?</h3>
            <p>Modern streaming services don't allow downloading music for offline portable players. MP3 Player Genie 
            fills this gap, letting parents:</p>
            <ul>
                <li>Control their children's music library</li>
                <li>Avoid constant internet connectivity requirements</li>
                <li>Reduce screen time and social media exposure</li>
                <li>Ensure age-appropriate content with built-in filters</li>
            </ul>
            
            <p>The application makes best efforts to download official audio versions of songs, though in some cases 
            music video audio might be used if no better source is available.</p>
            
            <p><small>MP3 Player Genie is open source software. Visit our 
            <a href="https://github.com/yourusername/mp3-player-genie">GitHub repository</a> 
            for more information.</small></p>
        """)
        layout.addWidget(description)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button) 