from pathlib import Path
import json
import logging
from typing import Any, Optional, Dict
import os
import sys

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self):
        # Get executable directory
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_dir = Path(sys.executable).parent
        else:
            # Running from source
            base_dir = Path(__file__).parent.parent.parent
            
        self.config_dir = base_dir
        self.config_file = self.config_dir / "config.json"
        self.config: Dict[str, Any] = {}
        
        # Load or create default config
        self._load_or_create()
        
    def _load_or_create(self):
        """Load existing config or create with defaults."""
        try:
            if self.config_file.exists():
                logger.debug("Loading config from %s", self.config_file)
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                logger.info("Creating new config with defaults")
                self._create_default_config()
                self.save()
                
        except Exception as e:
            logger.error("Failed to load config: %s", e)
            self._create_default_config()
            
    def _create_default_config(self):
        """Create default configuration."""
        self.config = {
            "downloads": {
                "base_dir": str(Path.home() / "Music" / "Downloaded"),
                "organize_by_artist": True,
                "audio_format": "mp3",
                "audio_quality": "192k",
                "fetch_metadata": True,
                "embed_thumbnail": True
            },
            "usb": {
                "auto_sync": True,
                "create_playlists": False,
                "auto_eject": False,
                "directory_structure": "Same as local"
            },
            "network": {
                "use_proxy": False,
                "proxy_host": "",
                "proxy_port": 8080,
                "max_downloads": 1
            }
        }
        
    def save(self):
        """Save current configuration to file."""
        try:
            logger.debug("Saving config to %s", self.config_file)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error("Failed to save config: %s", e)
            
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        try:
            return self.config[section][key]
        except KeyError:
            return default
            
    def set(self, section: str, key: str, value: Any):
        """Set a configuration value."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        
    def get_download_dir(self) -> Path:
        """Get the configured download directory."""
        return Path(self.get("downloads", "base_dir")).expanduser()
        
    def get_audio_format(self) -> str:
        """Get the configured audio format."""
        return self.get("downloads", "audio_format", "mp3")
        
    def get_audio_quality(self) -> str:
        """Get the configured audio quality."""
        return self.get("downloads", "audio_quality", "320k")
        
    def should_fetch_metadata(self) -> bool:
        """Check if metadata fetching is enabled."""
        return self.get("downloads", "fetch_metadata", True)
        
    def should_embed_thumbnail(self) -> bool:
        """Check if thumbnail embedding is enabled."""
        return self.get("downloads", "embed_thumbnail", True)
        
    def should_organize_by_artist(self) -> bool:
        """Check if organizing by artist is enabled."""
        return self.get("downloads", "organize_by_artist", True)
        
    def get_max_downloads(self) -> int:
        """Get maximum concurrent downloads."""
        return self.get("network", "max_downloads", 3)
        
    def get_proxy_settings(self) -> Optional[tuple[str, int]]:
        """Get proxy settings if enabled."""
        if self.get("network", "use_proxy", False):
            host = self.get("network", "proxy_host", "")
            port = self.get("network", "proxy_port", 8080)
            return (host, port)
        return None 