# MP3 Player Genie 🎵

A Windows app for downloading and organizing music. Built with Python and Qt. Currently in early development!

⚠️ **Note:** This is a work in progress and pretty buggy. Use at your own risk!

## What it does (or tries to do 😅)

- Download music with a modern-looking UI
- Search for songs and preview before downloading
- Auto-organize your music library
- Sync to USB drives (when it works)
- Show pretty progress bars and stuff
- Default to 192k audio quality

## You'll need

- Windows 10+
- Python 3.11+

## Want to try it?

### Quick way (when we have releases)
Coming soon! We'll have proper releases once it's more stable.

### Hacker way (if you're brave)

1. Get the basics:
```powershell
winget install Python.Python.3.11
winget install FFmpeg
```

2. Clone and set up:
```powershell
git clone https://github.com/lmacka/music-downloader.git
cd mp3-player-genie
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

3. Build it:
```powershell
python setup_windows.py
```

## How to use it

1. Launch it (if it launches 🤞)
2. Type a song name in the search box
3. Hit search and pick your song
4. Watch the progress bars move!

### Cool features (when they work)

- **Search:** Pretty good at finding the right song
- **Downloads:** Shows progress and can handle a few at once
- **USB Support:** Detects USB drives and can copy files over
- **Settings:** Lots of knobs to tweak if you're into that

## Project Structure
```
mp3-player-genie/
├── music_downloader/     # Where the magic happens
│   ├── core/            # The brain stuff
│   ├── gui/             # The pretty stuff
│   └── __main__.py      # The "on" button
├── tests/               # Some tests (need more!)
└── various setup files  # For making it installable
```

## Development

This is a hobby project using:
- Python 3.11+ (because new Python is best Python)
- PySide6 (Qt for the UI)
- Async/await (for that sweet non-blocking IO)
- Type hints (because we like to know what's what)

### Building from source

1. Get the dependencies:
```powershell
pip install -r requirements.txt
```

2. Cross your fingers and run:
```powershell
python setup_windows.py
```

This should:
- Make an exe with PyInstaller
- Put it in Program Files
- Create some shortcuts
- Add it to PATH

### Uninstalling

If it all goes wrong:
- Use Windows "Add or Remove Programs"
- Or run `uninstall_windows.py`
- Or just delete the folder
