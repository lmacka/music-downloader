import sys
import shutil
from pathlib import Path
from typing import Optional, List

class USBHandler:
    """Cross-platform USB drive handling."""
    
    @staticmethod
    def get_usb_drives() -> List[Path]:
        """Get available USB drives."""
        if sys.platform == 'win32':
            return USBHandler._get_windows_usb_drives()
        else:
            return USBHandler._get_linux_usb_drives()
    
    @staticmethod
    def _get_windows_usb_drives() -> List[Path]:
        """Get USB drives on Windows."""
        try:
            import win32api
            import win32file
            
            drives = []
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                try:
                    drive = f"{letter}:\\"
                    drive_type = win32file.GetDriveType(drive)
                    if drive_type == win32file.DRIVE_REMOVABLE:
                        path = Path(drive)
                        if path.exists():
                            drives.append(path)
                except Exception:
                    continue
            return drives
            
        except ImportError:
            # win32api not available
            return []
    
    @staticmethod
    def _get_linux_usb_drives() -> List[Path]:
        """Get USB drives on Linux."""
        try:
            import psutil
            
            drives = []
            for partition in psutil.disk_partitions():
                if 'removable' in partition.opts or '/media/' in partition.mountpoint:
                    path = Path(partition.mountpoint)
                    if path.exists():
                        drives.append(path)
            return drives
            
        except ImportError:
            # psutil not available
            return []
    
    @staticmethod
    def copy_to_usb(
        file_path: Path,
        artist: str,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """Copy a file to the first available USB drive."""
        try:
            # Get available USB drives
            drives = USBHandler.get_usb_drives()
            if not drives:
                return False
                
            # Use first available drive
            usb_drive = drives[0]
            
            # Create Music directory if needed
            music_dir = usb_drive / "Music"
            music_dir.mkdir(exist_ok=True)
            
            # Create artist directory
            artist_dir = music_dir / artist
            artist_dir.mkdir(exist_ok=True)
            
            # Copy file
            dest_path = artist_dir / file_path.name
            
            if progress_callback:
                progress_callback("Copying to USB...", 0)
                
            shutil.copy2(file_path, dest_path)
            
            if progress_callback:
                progress_callback("USB copy complete!", 1)
                
            return True
            
        except Exception as e:
            if progress_callback:
                progress_callback(f"USB copy failed: {e}", 0)
            return False
    
    @staticmethod
    def eject_drive(drive_path: Path) -> bool:
        """Safely eject a USB drive."""
        if sys.platform == 'win32':
            try:
                import win32api
                
                drive_letter = str(drive_path)[:2]
                win32api.GetVolumeInformation(drive_letter + "\\")
                return True
                
            except ImportError:
                return False
                
        else:  # Linux
            try:
                import subprocess
                
                result = subprocess.run(
                    ['udisksctl', 'unmount', '-b', str(drive_path)],
                    capture_output=True,
                    text=True
                )
                return result.returncode == 0
                
            except (ImportError, FileNotFoundError):
                return False 