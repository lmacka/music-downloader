# Create a shortcut to run the music downloader
$WshShell = New-Object -ComObject WScript.Shell

# Get the desktop path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Download Music.lnk"

# Create the shortcut
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -NoProfile -File `"$PSScriptRoot\download-music.ps1`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "shell32.dll,169"  # Music note icon from Windows
$shortcut.Description = "YouTube Music Downloader for MP3 Players"
$shortcut.Save()

Write-Host "Shortcut created on desktop: 'Download Music'" 