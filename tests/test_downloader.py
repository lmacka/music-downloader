import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from music_downloader.core.downloader import MusicDownloader, TrackMetadata

@pytest.fixture
def downloader():
    return MusicDownloader(Path("/tmp/test"), "test_user")

@pytest.fixture
def mock_progress_callback():
    return Mock()

@pytest.mark.asyncio
async def test_download_track_success(downloader, mock_progress_callback):
    """Test successful track download."""
    with patch("yt_dlp.YoutubeDL") as mock_ytdl:
        # Mock successful download
        mock_ytdl.return_value.download.return_value = 0
        mock_ytdl.return_value.extract_info.return_value = {
            "title": "Test Song",
            "uploader": "Test Artist",
            "duration": 180
        }
        
        result = await downloader.download_track("test_id", mock_progress_callback)
        assert result.exists()
        mock_progress_callback.assert_called_with("Download complete!", 1.0)

@pytest.mark.asyncio
async def test_download_track_metadata_failure(downloader, mock_progress_callback):
    """Test download succeeds even if metadata update fails."""
    with patch("yt_dlp.YoutubeDL") as mock_ytdl, \
         patch.object(downloader, "_update_metadata") as mock_update:
        # Mock successful download but failed metadata
        mock_ytdl.return_value.download.return_value = 0
        mock_ytdl.return_value.extract_info.return_value = {
            "title": "Test Song",
            "uploader": "Test Artist",
            "duration": 180
        }
        mock_update.side_effect = Exception("Metadata update failed")
        
        result = await downloader.download_track("test_id", mock_progress_callback)
        assert result.exists()
        mock_progress_callback.assert_any_call(
            "Warning: Metadata update failed, but download succeeded", 
            0.95
        )

@pytest.mark.asyncio
async def test_download_track_cancelled(downloader, mock_progress_callback):
    """Test download cancellation."""
    with patch("yt_dlp.YoutubeDL") as mock_ytdl:
        # Simulate cancellation
        downloader._cancelled = True
        
        with pytest.raises(asyncio.CancelledError):
            await downloader.download_track("test_id", mock_progress_callback)

@pytest.mark.asyncio
async def test_search_track_no_results(downloader):
    """Test search with no results."""
    with patch("yt_dlp.YoutubeDL") as mock_ytdl:
        mock_ytdl.return_value.extract_info.return_value = {"entries": []}
        results = []
        async for result in downloader.search_track("nonexistent song"):
            results.append(result)
        assert len(results) == 0

@pytest.mark.asyncio
async def test_search_track_with_results(downloader):
    """Test search with results."""
    with patch("yt_dlp.YoutubeDL") as mock_ytdl:
        mock_ytdl.return_value.extract_info.return_value = {
            "entries": [{
                "title": "Test Song",
                "uploader": "Test Artist",
                "duration": 180,
                "id": "test_id"
            }]
        }
        results = []
        async for result in downloader.search_track("test song"):
            results.append(result)
        assert len(results) == 1
        assert results[0]["title"] == "Test Song" 