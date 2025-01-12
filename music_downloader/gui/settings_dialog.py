from pathlib import Path
from typing import Optional
import logging
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QCheckBox, QSpinBox,
    QPushButton, QTabWidget, QFileDialog,
    QComboBox, QFormLayout, QGroupBox, QToolButton
)
from PySide6.QtCore import Qt, Signal
from ..core.config import ConfigManager

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """Settings dialog window."""
    
    # Signals
    settings_changed = Signal()  # Emitted when settings are applied
    
    def __init__(self, config: ConfigManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        
        # Tab widget
        tabs = QTabWidget()
        
        # Downloads tab
        downloads_tab = QWidget()
        downloads_layout = QVBoxLayout(downloads_tab)
        
        # Download location group
        location_group = QGroupBox("Download Location")
        location_layout = QFormLayout()
        
        self.base_dir_input = QLineEdit()
        browse_button = QToolButton()
        browse_button.setText("...")
        browse_button.clicked.connect(self._browse_location)
        
        location_row = QHBoxLayout()
        location_row.addWidget(self.base_dir_input)
        location_row.addWidget(browse_button)
        
        location_layout.addRow("Base Directory:", location_row)
        
        self.organize_by_artist = QCheckBox("Organize by Artist")
        self.organize_by_artist.setChecked(True)
        location_layout.addRow("", self.organize_by_artist)
        
        location_group.setLayout(location_layout)
        downloads_layout.addWidget(location_group)
        
        # Audio quality group
        quality_group = QGroupBox("Audio Quality")
        quality_layout = QFormLayout()
        
        self.audio_format = QComboBox()
        self.audio_format.addItems(["mp3", "m4a", "opus", "wav"])
        quality_layout.addRow("Format:", self.audio_format)
        
        self.audio_quality = QComboBox()
        self.audio_quality.addItems(["320k", "256k", "192k", "128k"])
        quality_layout.addRow("Bitrate:", self.audio_quality)
        
        quality_group.setLayout(quality_layout)
        downloads_layout.addWidget(quality_group)
        
        # Metadata group
        metadata_group = QGroupBox("Metadata")
        metadata_layout = QFormLayout()
        
        self.fetch_metadata = QCheckBox("Fetch additional metadata")
        self.fetch_metadata.setChecked(True)
        metadata_layout.addRow("", self.fetch_metadata)
        
        self.embed_thumbnail = QCheckBox("Embed thumbnail in file")
        self.embed_thumbnail.setChecked(True)
        metadata_layout.addRow("", self.embed_thumbnail)
        
        metadata_group.setLayout(metadata_layout)
        downloads_layout.addWidget(metadata_group)
        
        # Content filter group
        filter_group = QGroupBox("Content Filter")
        filter_layout = QFormLayout()
        
        self.enable_filter = QCheckBox("Enable content filter")
        self.enable_filter.setChecked(True)
        filter_layout.addRow("", self.enable_filter)
        
        filter_group.setLayout(filter_layout)
        downloads_layout.addWidget(filter_group)
        
        downloads_layout.addStretch()
        tabs.addTab(downloads_tab, "Downloads")
        
        # USB tab
        usb_tab = QWidget()
        usb_layout = QVBoxLayout(usb_tab)
        
        # USB sync group
        usb_group = QGroupBox("USB Synchronization")
        usb_form = QFormLayout()
        
        self.auto_sync = QCheckBox("Automatically sync to USB")
        self.auto_sync.setChecked(True)
        usb_form.addRow("", self.auto_sync)
        
        self.create_playlists = QCheckBox("Create playlists on USB")
        usb_form.addRow("", self.create_playlists)
        
        self.auto_eject = QCheckBox("Auto-eject after sync")
        usb_form.addRow("", self.auto_eject)
        
        usb_group.setLayout(usb_form)
        usb_layout.addWidget(usb_group)
        
        # USB organization group
        usb_org_group = QGroupBox("USB Organization")
        usb_org_form = QFormLayout()
        
        self.usb_dir_structure = QComboBox()
        self.usb_dir_structure.addItems([
            "Same as local",
            "Flat structure",
            "Artist/Album/Track",
            "Genre/Artist/Track"
        ])
        usb_org_form.addRow("Directory Structure:", self.usb_dir_structure)
        
        usb_org_group.setLayout(usb_org_form)
        usb_layout.addWidget(usb_org_group)
        
        usb_layout.addStretch()
        tabs.addTab(usb_tab, "USB")
        
        # Network tab
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        
        # Proxy group
        proxy_group = QGroupBox("Proxy Settings")
        proxy_form = QFormLayout()
        
        self.use_proxy = QCheckBox("Use proxy")
        proxy_form.addRow("", self.use_proxy)
        
        self.proxy_host = QLineEdit()
        self.proxy_host.setEnabled(False)
        proxy_form.addRow("Host:", self.proxy_host)
        
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_port.setValue(8080)
        self.proxy_port.setEnabled(False)
        proxy_form.addRow("Port:", self.proxy_port)
        
        self.use_proxy.toggled.connect(self.proxy_host.setEnabled)
        self.use_proxy.toggled.connect(self.proxy_port.setEnabled)
        
        proxy_group.setLayout(proxy_form)
        network_layout.addWidget(proxy_group)
        
        # Rate limiting group
        rate_group = QGroupBox("Rate Limiting")
        rate_form = QFormLayout()
        
        self.max_downloads = QSpinBox()
        self.max_downloads.setRange(1, 10)
        self.max_downloads.setValue(3)
        rate_form.addRow("Max Concurrent Downloads:", self.max_downloads)
        
        rate_group.setLayout(rate_form)
        network_layout.addWidget(rate_group)
        
        network_layout.addStretch()
        tabs.addTab(network_tab, "Network")
        
        layout.addWidget(tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(apply_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
    def _browse_location(self):
        """Open file dialog to choose base download location."""
        current = Path(self.base_dir_input.text()).expanduser()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Download Location",
            str(current),
            QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.base_dir_input.setText(directory)
            
    def _load_settings(self):
        """Load current settings into the UI."""
        # Downloads
        self.base_dir_input.setText(str(self.config.get_download_dir()))
        self.organize_by_artist.setChecked(self.config.should_organize_by_artist())
        self.audio_format.setCurrentText(self.config.get_audio_format())
        self.audio_quality.setCurrentText(self.config.get_audio_quality())
        self.fetch_metadata.setChecked(self.config.should_fetch_metadata())
        self.embed_thumbnail.setChecked(self.config.should_embed_thumbnail())
        
        # USB
        self.auto_sync.setChecked(self.config.get("usb", "auto_sync", True))
        self.create_playlists.setChecked(self.config.get("usb", "create_playlists", False))
        self.auto_eject.setChecked(self.config.get("usb", "auto_eject", False))
        self.usb_dir_structure.setCurrentText(
            self.config.get("usb", "directory_structure", "Same as local")
        )
        
        # Network
        self.use_proxy.setChecked(self.config.get("network", "use_proxy", False))
        self.proxy_host.setText(self.config.get("network", "proxy_host", ""))
        self.proxy_port.setValue(self.config.get("network", "proxy_port", 8080))
        self.max_downloads.setValue(self.config.get_max_downloads())
        
        # Content filter
        self.enable_filter.setChecked(self.config.get("downloads", "enable_filter", True))
        
    def _apply_settings(self):
        """Apply the current settings."""
        # Downloads
        self.config.set("downloads", "base_dir", self.base_dir_input.text())
        self.config.set("downloads", "organize_by_artist", self.organize_by_artist.isChecked())
        self.config.set("downloads", "audio_format", self.audio_format.currentText())
        self.config.set("downloads", "audio_quality", self.audio_quality.currentText())
        self.config.set("downloads", "fetch_metadata", self.fetch_metadata.isChecked())
        self.config.set("downloads", "embed_thumbnail", self.embed_thumbnail.isChecked())
        
        # USB
        self.config.set("usb", "auto_sync", self.auto_sync.isChecked())
        self.config.set("usb", "create_playlists", self.create_playlists.isChecked())
        self.config.set("usb", "auto_eject", self.auto_eject.isChecked())
        self.config.set("usb", "directory_structure", self.usb_dir_structure.currentText())
        
        # Network
        self.config.set("network", "use_proxy", self.use_proxy.isChecked())
        self.config.set("network", "proxy_host", self.proxy_host.text())
        self.config.set("network", "proxy_port", self.proxy_port.value())
        self.config.set("network", "max_downloads", self.max_downloads.value())
        
        # Content filter
        self.config.set("downloads", "enable_filter", self.enable_filter.isChecked())
        
        # Save to file
        self.config.save()
        self.settings_changed.emit()
        
    def get_download_dir(self) -> Path:
        """Get the configured download directory."""
        return Path(self.base_dir_input.text()).expanduser()
        
    def get_audio_format(self) -> str:
        """Get the configured audio format."""
        return self.audio_format.currentText()
        
    def get_audio_quality(self) -> str:
        """Get the configured audio quality."""
        return self.audio_quality.currentText()
        
    def should_fetch_metadata(self) -> bool:
        """Check if metadata fetching is enabled."""
        return self.fetch_metadata.isChecked()
        
    def should_embed_thumbnail(self) -> bool:
        """Check if thumbnail embedding is enabled."""
        return self.embed_thumbnail.isChecked()
        
    def should_organize_by_artist(self) -> bool:
        """Check if organizing by artist is enabled."""
        return self.organize_by_artist.isChecked()
        
    def get_max_downloads(self) -> int:
        """Get maximum concurrent downloads."""
        return self.max_downloads.value()
        
    def get_proxy_settings(self) -> Optional[tuple[str, int]]:
        """Get proxy settings if enabled."""
        if self.use_proxy.isChecked():
            return (self.proxy_host.text(), self.proxy_port.value())
        return None 