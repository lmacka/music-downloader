import os
import sys
import shutil
import subprocess
from pathlib import Path
import winreg
import ctypes

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

def remove_from_path(directory: Path):
    """Remove directory from system PATH."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_ALL_ACCESS
        ) as key:
            # Get current PATH
            path = winreg.QueryValueEx(key, "PATH")[0]
            
            # Remove our directory
            paths = path.split(";")
            paths = [p for p in paths if p != str(directory)]
            new_path = ";".join(paths)
            
            # Update PATH
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            
            # Notify the system of the change
            subprocess.run(
                'setx PATH "%PATH%"',
                shell=True,
                capture_output=True
            )
    except Exception as e:
        print(f"Warning: Failed to update PATH: {e}")

def main():
    """Main uninstall function."""
    # Ensure running as admin
    if not is_admin():
        run_as_admin()
        
    print("Uninstalling Music Downloader...")
    
    # Get installation directory
    install_dir = Path(os.environ["ProgramFiles"]) / "Music Downloader"
    
    # Remove shortcuts
    print("\nRemoving shortcuts...")
    
    # Desktop shortcut
    desktop_shortcut = Path(os.environ["USERPROFILE"]) / "Desktop" / "Music Downloader.lnk"
    if desktop_shortcut.exists():
        desktop_shortcut.unlink()
        
    # Start menu shortcuts
    start_menu_dir = Path(os.environ["ProgramData"]) / "Microsoft/Windows/Start Menu/Programs/Music Downloader"
    if start_menu_dir.exists():
        shutil.rmtree(start_menu_dir)
        
    # Remove from PATH
    print("\nUpdating system PATH...")
    remove_from_path(install_dir)
    
    # Remove installation directory
    print("\nRemoving program files...")
    if install_dir.exists():
        shutil.rmtree(install_dir)
        
    print("\nUninstallation complete!")
    print("\nMusic Downloader has been removed from your system.")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError during uninstallation: {e}")
        input("\nPress Enter to exit...") 