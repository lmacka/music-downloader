from pathlib import Path
import logging
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox,
    QStyle, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette, QFont
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

logger = logging.getLogger(__name__)

class MetadataDialog(QDialog):
    """Dialog for displaying track metadata."""
    
    def __init__(self, metadata: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Track Metadata")
        self.setMinimumWidth(400)
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Create table
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        # Add metadata to table
        table.setRowCount(len(metadata))
        for i, (key, value) in enumerate(sorted(metadata.items())):
            # Clean up key for display
            display_key = key.replace('_', ' ').title()
            
            key_item = QTableWidgetItem(display_key)
            value_item = QTableWidgetItem(str(value))
            
            # Make items read-only
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            table.setItem(i, 0, key_item)
            table.setItem(i, 1, value_item)
        
        layout.addWidget(table)
        
        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

class TaskCard(QFrame):
    """Card widget for displaying a download task."""
    
    # Signals
    retry = Signal(str)  # task_id
    remove = Signal(str)  # task_id
    cancel = Signal(str)  # task_id
    
    def __init__(self, task_id: str, title: str, artist: str):
        """Initialize the task card."""
        super().__init__()
        self.task_id = task_id
        self.title = title
        self.artist = artist
        self.status = ""
        self.file_path: Optional[Path] = None
        self.metadata: Optional[Dict[str, str]] = None
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Title and artist
        title_label = QLabel(f"<b>{title}</b>")
        artist_label = QLabel(artist)
        layout.addWidget(title_label)
        layout.addWidget(artist_label)
        
        # Status and progress
        status_layout = QHBoxLayout()
        self.status_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setMinimum(0)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        layout.addLayout(status_layout)
        
        # File info
        self.file_info_label = QLabel()
        self.file_info_label.hide()
        layout.addWidget(self.file_info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(lambda: self.cancel.emit(self.task_id))
        self.cancel_button.hide()
        
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(lambda: self.retry.emit(self.task_id))
        self.retry_button.hide()
        
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(lambda: self.remove.emit(self.task_id))
        self.remove_button.hide()
        
        self.metadata_button = QPushButton("Show Metadata")
        self.metadata_button.clicked.connect(self._show_metadata)
        self.metadata_button.hide()
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.retry_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.metadata_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Set up appearance
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setAutoFillBackground(True)
        
    def _show_metadata(self):
        """Show the metadata dialog."""
        if self.metadata:
            dialog = MetadataDialog(self.metadata, self)
            dialog.exec()
        
    def set_status(self, status: str, progress: float = 0):
        """Update the status and progress."""
        self.status = status
        self.progress_bar.setValue(int(progress * 100))
        
        # Update status label with better formatting
        if progress > 0:
            status_text = f"{status}"
            if "..." in status:  # For ongoing operations
                self.status_label.setStyleSheet("color: #2196F3;")  # Blue for active
                self.cancel_button.setVisible(True)  # Show cancel during active operations
                self.metadata_button.hide()
            elif "complete" in status.lower() or "success" in status.lower():
                self.status_label.setStyleSheet("color: #4CAF50;")  # Green for success
                self.cancel_button.setVisible(False)
                if self.metadata:
                    self.metadata_button.show()
            elif "error" in status.lower() or "failed" in status.lower():
                self.status_label.setStyleSheet("color: #F44336;")  # Red for errors
                self.cancel_button.setVisible(False)
                self.metadata_button.hide()
            else:
                self.status_label.setStyleSheet("")  # Default color
        else:
            status_text = status
            self.cancel_button.setVisible(False)
            self.metadata_button.hide()
            
        # Set status text
        self.status_label.setText(status_text)
        
        # Show/hide controls based on status
        is_error = "error" in status.lower() or "failed" in status.lower()
        is_complete = progress >= 1.0 or "complete" in status.lower()
        
        self.retry_button.setVisible(is_error)
        self.remove_button.setVisible(is_complete or is_error)
        
    def set_file_path(self, path: Path, metadata: Optional[Dict[str, str]] = None):
        """Set the downloaded file path and update info."""
        self.file_path = path
        self.metadata = metadata
        
        if path and path.exists():
            try:
                audio = MP3(path)
                size_mb = path.stat().st_size / (1024 * 1024)
                duration = audio.info.length
                minutes = int(duration // 60)
                seconds = int(duration % 60)
                
                info_text = (
                    f"Size: {size_mb:.1f} MB | "
                    f"Duration: {minutes}:{seconds:02d} | "
                    f"Format: MP3"
                )
                self.file_info_label.setText(info_text)
                self.file_info_label.show()
                
                if metadata:
                    self.metadata_button.show()
                    
            except Exception as e:
                logger.error("Failed to read audio file info: %s", e)
                self.file_info_label.hide()
                
    def set_completed(self, file_path: Optional[Path] = None, metadata: Optional[Dict[str, str]] = None):
        """Mark the task as completed."""
        if file_path:
            self.set_file_path(file_path, metadata)
        self.set_status("Download complete!", 1.0)
        self.cancel_button.hide()
        if metadata:
            self.metadata_button.show()
        
    def set_error(self, error: str):
        """Mark the task as failed with an error."""
        self.set_status(f"Error: {error}", 0)
        self.retry_button.show()
        self.remove_button.show()
        self.cancel_button.hide()
        self.metadata_button.hide()
        
    def set_cancelled(self):
        """Mark the task as cancelled."""
        self.set_status("Cancelled", 0)
        self.remove_button.show()
        self.cancel_button.hide()
        self.metadata_button.hide() 