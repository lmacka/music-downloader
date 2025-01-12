import sys
import asyncio
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .gui.main_window import MainWindow

def setup_logging():
    """Set up logging configuration."""
    log_dir = Path.home() / ".music-downloader" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create rotating file handler
    log_file = log_dir / "music-downloader.log"
    
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for more detailed logs
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also output to console
        ]
    )
    
    # Set up specific loggers
    logging.getLogger('yt_dlp').setLevel(logging.INFO)  # Reduce yt-dlp noise
    logging.getLogger('PIL').setLevel(logging.INFO)     # Reduce Pillow noise
    
    logger = logging.getLogger(__name__)
    logger.debug("Logging initialized. Log file: %s", log_file)

def main():
    """Main entry point."""
    # Set up logging
    setup_logging()
    
    # Enable high DPI scaling using newer attributes
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for consistent look
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 