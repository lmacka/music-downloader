import os
import sys
import shutil
import subprocess
from pathlib import Path
import winreg
import ctypes
from typing import Optional

def is_admin() -> bool:
    """Check if the script is running with admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with admin privileges if needed."""
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([script] + sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        sys.exit(0 if ret > 32 else ret)

def create_shortcut(
    target: Path,
    shortcut_path: Path,
    description: str,
    icon_path: Optional[Path] = None
) -> bool:
    """Create a Windows shortcut (.lnk file)."""
    try:
        import win32com.client
        
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath = str(target)
        shortcut.Description = description
        if icon_path:
            shortcut.IconLocation = str(icon_path)
        shortcut.save()
        return True
    except Exception as e:
        print(f"Failed to create shortcut: {e}")
        return False

def main():
    """Main setup function."""
    # Ensure running as admin
    if not is_admin():
        run_as_admin()
        
    print("Setting up Music Downloader...")
    
    # Create build directory if it doesn't exist
    build_dir = Path("build")
    build_dir.mkdir(exist_ok=True)
    
    # Build the executable using PyInstaller
    print("\nBuilding executable...")
    subprocess.run(
        ["pyinstaller", "--clean", "music_downloader.spec"],
        check=True
    )
    
    # Get paths
    exe_path = Path("dist/MusicDownloader.exe")
    if not exe_path.exists():
        print("Error: Failed to build executable")
        sys.exit(1)
        
    # Create program files directory
    install_dir = Path(os.environ["ProgramFiles"]) / "Music Downloader"
    install_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy executable and dependencies
    print("\nInstalling files...")
    shutil.copy2(exe_path, install_dir / "MusicDownloader.exe")
    
    # Create shortcuts
    print("\nCreating shortcuts...")
    
    # Desktop shortcut
    desktop_dir = Path(os.environ["USERPROFILE"]) / "Desktop"
    create_shortcut(
        target=install_dir / "MusicDownloader.exe",
        shortcut_path=desktop_dir / "Music Downloader.lnk",
        description="Download and organize music",
        icon_path=install_dir / "MusicDownloader.exe"
    )
    
    # Start menu shortcut
    start_menu_dir = Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs"
    start_menu_dir = start_menu_dir / "Music Downloader"
    start_menu_dir.mkdir(exist_ok=True)
    
    create_shortcut(
        target=install_dir / "MusicDownloader.exe",
        shortcut_path=start_menu_dir / "Music Downloader.lnk",
        description="Download and organize music",
        icon_path=install_dir / "MusicDownloader.exe"
    )
    
    # Create uninstaller shortcut
    create_shortcut(
        target=install_dir / "uninstall.exe",
        shortcut_path=start_menu_dir / "Uninstall Music Downloader.lnk",
        description="Uninstall Music Downloader"
    )
    
    # Add to PATH
    print("\nUpdating system PATH...")
    try:
        # Open the environment variable registry key
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_ALL_ACCESS
        ) as key:
            # Get current PATH
            path = winreg.QueryValueEx(key, "PATH")[0]
            
            # Add our directory if not already present
            if str(install_dir) not in path:
                new_path = f"{path};{install_dir}"
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                
                # Notify the system of the change
                subprocess.run(
                    'setx PATH "%PATH%"',
                    shell=True,
                    capture_output=True
                )
    except Exception as e:
        print(f"Warning: Failed to update PATH: {e}")
    
    print("\nInstallation complete!")
    print(f"\nMusic Downloader has been installed to: {install_dir}")
    print("You can now launch it from:")
    print("1. The desktop shortcut")
    print("2. The Start Menu")
    print("3. Running 'MusicDownloader' from any terminal")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError during setup: {e}")
        input("\nPress Enter to exit...") 