from pathlib import Path
from typing import Optional, Dict
import asyncio
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog,
    QCheckBox, QMessageBox, QToolButton, QStyle,
    QStatusBar
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QThread, QObject
from PySide6.QtGui import QFont
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3

from ..core.downloader import MusicDownloader, ProgressCallback
from ..core.usb import USBHandler
from ..core.config import ConfigManager
from .task_manager import TaskManager
from .settings_dialog import SettingsDialog
from .about_dialog import AboutDialog
from .search_dialog import SearchResultsDialog

# QMessageBox button constants
MSG_OK = QMessageBox.StandardButton.Ok
MSG_YES = QMessageBox.StandardButton.Yes
MSG_NO = QMessageBox.StandardButton.No

logger = logging.getLogger(__name__)

class AsyncHelper(QObject):
    """Helper class to run async code in Qt."""
    
    def __init__(self):
        super().__init__()
        logger.debug("Initializing AsyncHelper")
        self._loop = asyncio.new_event_loop()
        
    def cleanup(self):
        """Clean up resources."""
        logger.debug("Starting AsyncHelper cleanup")
        if self._loop and self._loop.is_running():
            logger.debug("Stopping running event loop")
            self._loop.stop()
        if self._loop and not self._loop.is_closed():
            logger.debug("Closing event loop")
            self._loop.close()
        logger.info("AsyncHelper cleanup complete")

class DownloadWorker(QThread):
    """Background worker for downloads."""
    progress = Signal(str, float)  # status, progress
    finished = Signal(bool, str, dict)   # success, result/error, metadata
    
    def __init__(self, downloader: MusicDownloader, video_id: str):
        super().__init__()
        self.downloader = downloader
        self.video_id = video_id
        self._is_cancelled = False
        
    def run(self):
        """Run the download in background."""
        try:
            logger.debug("Starting download for video ID: %s", self.video_id)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Create progress callback that matches ProgressCallback protocol
            def progress_callback(status: str, progress: float = 0) -> None:
                if not self._is_cancelled:
                    logger.debug("Download progress: %s (%.1f%%)", status, progress * 100)
                    self.progress.emit(status, progress)
            
            # Download the track
            file_path = loop.run_until_complete(
                self.downloader.download_track(
                    self.video_id,
                    progress_callback
                )
            )
            
            if self._is_cancelled:
                logger.info("Download cancelled for video ID: %s", self.video_id)
                self.finished.emit(False, "Cancelled", {})
            else:
                logger.info("Download completed: %s", file_path)
                # Get metadata from audio file
                try:
                    metadata = {}
                    
                    # Try to get ID3 tags first
                    try:
                        tags = EasyID3(file_path)
                        if tags:
                            # Get standard ID3 tags
                            for key in ['title', 'artist', 'album', 'date', 'genre']:
                                if key in tags:
                                    metadata[key] = tags[key][0]
                            
                    except Exception as e:
                        logger.warning("Failed to read ID3 tags: %s", e)
                    
                    # Add file info
                    file_stat = Path(file_path).stat()
                    size_mb = file_stat.st_size / (1024 * 1024)
                    
                    metadata.update({
                        'file_path': str(file_path),
                        'format': 'MP3',
                        'size': f"{size_mb:.1f} MB",
                        'modified': file_stat.st_mtime
                    })
                    
                    logger.debug("Extracted metadata: %s", metadata)
                    self.finished.emit(True, str(file_path), metadata)
                    
                except Exception as e:
                    logger.error("Failed to read metadata: %s", e)
                    # Still emit success but with empty metadata
                    self.finished.emit(True, str(file_path), {})
            
        except Exception as e:
            logger.exception("Download failed")
            self.finished.emit(False, str(e), {})
            
        finally:
            loop.close()
            
    def cancel(self):
        """Cancel the download."""
        logger.info("Cancelling download for video ID: %s", self.video_id)
        self._is_cancelled = True

class SearchWorker(QThread):
    """Worker thread for searching tracks."""
    
    # Signals
    result = Signal(dict)  # Single result
    results_ready = Signal(list)  # All results
    error = Signal(str)
    finished = Signal()
    
    def __init__(self, downloader: MusicDownloader, query: str):
        super().__init__()
        self.downloader = downloader
        self.query = query
        self._cancelled = False
        
    def run(self):
        """Run the search."""
        try:
            results = []
            async def search():
                async for result in self.downloader.search_track(self.query):
                    if self._cancelled:
                        break
                    results.append(result)
                return results
                
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(search())
            loop.close()
            
            if not self._cancelled and results:
                self.results_ready.emit(results[:10])  # Limit to top 10 results
                
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
        finally:
            if not self._cancelled:
                self.finished.emit()
    
    def cancel(self):
        """Cancel the search."""
        self._cancelled = True

class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize state
        self.config = ConfigManager()
        self.downloader = self._create_downloader()
        self.active_downloads: Dict[str, DownloadWorker] = {}
        self.search_worker: Optional[SearchWorker] = None
        
        # Initialize UI
        self._setup_ui()
        
        # Set up USB check timer
        self.usb_timer = QTimer(self)
        self.usb_timer.timeout.connect(self._check_usb)
        self.usb_timer.start(5000)  # Check every 5 seconds
        
        # Set window properties
        self.setWindowTitle("MP3 Player Genie")
        self.setMinimumSize(800, 600)
        
        logger.info("Main window initialized")
        
    def _create_downloader(self) -> MusicDownloader:
        """Create a new downloader instance."""
        # Get download directory from config or use default
        default_dir = Path.home() / "Music" / "Downloaded"
        music_dir = Path(self.config.get("downloads", "base_dir", str(default_dir)))
        
        # Ensure directory exists
        music_dir.mkdir(parents=True, exist_ok=True)
        
        return MusicDownloader(music_dir)
        
    def _setup_ui(self):
        """Set up the user interface."""
        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Search section
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter artist and song name...")
        self.search_input.returnPressed.connect(self._handle_search)
        search_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._handle_search)
        search_layout.addWidget(self.search_button)
        
        # Settings button
        settings_button = QPushButton()
        settings_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton))
        settings_button.setToolTip("Settings")
        settings_button.clicked.connect(self._show_settings)
        search_layout.addWidget(settings_button)
        
        layout.addLayout(search_layout)
        
        # Download location
        location_layout = QHBoxLayout()
        
        location_label = QLabel("Download Location:")
        location_layout.addWidget(location_label)
        
        self.location_input = QLineEdit()
        self.location_input.setText(str(Path.home() / "Music" / "Downloaded"))
        self.location_input.textChanged.connect(self._create_downloader)
        location_layout.addWidget(self.location_input)
        
        browse_button = QToolButton()
        browse_button.setText("...")
        browse_button.clicked.connect(self._browse_location)
        location_layout.addWidget(browse_button)
        
        layout.addLayout(location_layout)
        
        # USB checkbox
        usb_layout = QHBoxLayout()
        
        self.usb_checkbox = QCheckBox("Copy to USB when available")
        self.usb_checkbox.setChecked(True)
        usb_layout.addWidget(self.usb_checkbox)
        
        usb_layout.addStretch()
        
        layout.addLayout(usb_layout)
        
        # Task manager
        self.task_manager = TaskManager()
        layout.addWidget(self.task_manager, stretch=1)
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
    def _browse_location(self):
        """Open file dialog to choose download location."""
        current = Path(self.location_input.text()).expanduser()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Download Location",
            str(current),
            QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.location_input.setText(directory)
            self.downloader = self._create_downloader()
            
    def _handle_search(self):
        """Handle search button click."""
        query = self.search_input.text().strip()
        if not query:
            return
            
        logger.debug("Starting search for: %s", query)
        self.statusBar().showMessage("Searching...")
            
        # Disable UI elements
        self.search_button.setEnabled(False)
        self.search_input.setEnabled(False)
        
        # Start search in background
        self.search_worker = SearchWorker(self.downloader, query)
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.error.connect(self._on_search_error)
        self.search_worker.finished.connect(self._on_search_complete)
        self.search_worker.start()
        
    def _on_search_complete(self):
        """Re-enable UI elements after search completes."""
        logger.debug("Search completed")
        self.search_button.setEnabled(True)
        self.search_input.setEnabled(True)
        
        # Clean up worker
        if self.search_worker:
            self.search_worker.deleteLater()
            self.search_worker = None
            
    def _on_search_results(self, results: list):
        """Handle search results."""
        logger.debug("Received %d search results", len(results))
        
        if not results:
            self.statusBar().showMessage("No results found")
            return
            
        # Show search results dialog
        dialog = SearchResultsDialog(results, self)
        dialog.track_selected.connect(self._on_track_selected)
        dialog.exec()
        
        # Clear search
        self.search_input.clear()
    
    def _on_track_selected(self, result: dict):
        """Handle track selection."""
        logger.debug("Track selected: %s", result['title'])
        
        # Extract title and artist
        title = result['title']
        artist = result.get('channel', '')
        
        # Start download
        self._start_download(result['id'], title, artist)
        self.statusBar().showMessage("Download started")
        
    def _on_search_error(self, error: str):
        """Handle search error."""
        logger.error("Search error: %s", error)
        self.statusBar().showMessage("Search failed")
        QMessageBox.warning(
            self,
            "Search Error",
            f"Failed to search: {error}",
            MSG_OK,
            MSG_OK  # Default button
        )
        
    def _start_download(self, video_id: str, title: str, artist: str):
        """Start downloading a track."""
        # Create task
        task_id = self.task_manager.create_task(title, artist)
        
        # Create and start worker
        worker = DownloadWorker(self.downloader, video_id)
        worker.progress.connect(
            lambda status, progress: self._on_download_progress(task_id, status, progress)
        )
        worker.finished.connect(
            lambda success, result, metadata: self._on_download_finished(task_id, success, result, metadata)
        )
        
        # Store worker
        self.active_downloads[task_id] = worker
        
        # Start download
        worker.start()
            
    def _copy_to_usb(self, file_path: Path, task_id: str):
        """Copy downloaded file to USB drive."""
        try:
            # Create progress callback that matches ProgressCallback protocol
            def progress_callback(status: str, progress: float = 0) -> None:
                self.task_manager.update_task(task_id, status, progress)
                
            if USBHandler.copy_to_usb(
                file_path,
                file_path.parent.name,  # Artist directory name
                progress_callback
            ):
                self.statusBar().showMessage("Copied to USB drive")
            else:
                self.statusBar().showMessage("No USB drive found")
                
        except Exception as e:
            self.statusBar().showMessage("Failed to copy to USB")
            self.task_manager.fail_task(task_id, f"USB copy failed: {str(e)}")
            
    @Slot()
    def _check_usb(self):
        """Check for USB drive presence and update checkbox."""
        drives = USBHandler.get_usb_drives()
        self.usb_checkbox.setEnabled(bool(drives))
        
    def closeEvent(self, event):
        """Handle application close."""
        logger.debug("Starting application shutdown sequence")
        
        # Stop USB check timer
        if hasattr(self, 'usb_timer'):
            logger.debug("Stopping USB check timer")
            self.usb_timer.stop()
        
        # Cancel any active search
        if self.search_worker and self.search_worker.isRunning():
            logger.debug("Cancelling active search")
            self.search_worker.cancel()
            self.search_worker.wait()
            
        if self.active_downloads:
            logger.debug("Active downloads found: %d", len(self.active_downloads))
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Downloads are still in progress. Are you sure you want to exit?",
                MSG_YES | MSG_NO,
                MSG_NO
            )
            
            if reply == MSG_NO:
                logger.debug("User cancelled shutdown - active downloads")
                event.ignore()
                return
                
            # Cancel active downloads
            logger.debug("Cancelling active downloads")
            for task_id, worker in self.active_downloads.items():
                logger.debug("Cancelling download task: %s", task_id)
                worker.cancel()
                worker.wait()
                
            # Clear active downloads
            self.active_downloads.clear()
                
        # Check for USB drives that need ejecting
        drives = USBHandler.get_usb_drives()
        if drives:
            logger.debug("Found USB drives to eject: %s", drives)
            reply = QMessageBox.question(
                self,
                "USB Drive",
                "Would you like to safely eject USB drives before closing?",
                MSG_YES | MSG_NO,
                MSG_YES
            )
            
            if reply == MSG_YES:
                for drive in drives:
                    logger.debug("Attempting to eject drive: %s", drive)
                    if USBHandler.eject_drive(drive):
                        logger.info("Successfully ejected drive: %s", drive)
                        self.statusBar().showMessage(f"Ejected {drive}")
                    else:
                        logger.error("Failed to eject drive: %s", drive)
                        QMessageBox.warning(
                            self,
                            "Eject Failed",
                            f"Failed to eject {drive}",
                            MSG_OK,
                            MSG_OK  # Default button
                        )
                        
        logger.info("Application shutdown complete")
        event.accept() 
        
    def _show_settings(self):
        """Show the settings dialog."""
        dialog = SettingsDialog(self.config, self)
        dialog.settings_changed.connect(self._on_settings_changed)
        
        if dialog.exec():
            self._on_settings_changed()
            
    def _on_settings_changed(self):
        """Handle settings changes."""
        # Update UI
        self.location_input.setText(str(self.config.get_download_dir()))
        self.usb_checkbox.setChecked(self.config.get("usb", "auto_sync", True))
        
        # Reinitialize downloader with new settings
        self.downloader = self._create_downloader()
        
        # Update status
        self.statusBar().showMessage("Settings updated", 3000)
        
    def _show_about(self):
        """Show the About dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    def _on_download_progress(self, task_id: str, status: str, progress: float):
        """Handle download progress updates."""
        self.task_manager.update_task(task_id, status, progress)
        
    def _on_download_finished(self, task_id: str, success: bool, result: str, metadata: dict):
        """Handle download completion."""
        worker = self.active_downloads.pop(task_id, None)
        
        if success:
            # Pass the file path and metadata when completing
            self.task_manager.complete_task(task_id, Path(result), metadata)
            
            # Copy to USB if enabled
            if self.usb_checkbox.isChecked():
                self._copy_to_usb(Path(result), task_id)
        else:
            self.task_manager.fail_task(task_id, result)

# ... rest of the file ... 