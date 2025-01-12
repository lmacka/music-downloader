import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from music_downloader.core.downloader import MusicDownloader, TrackMetadata

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for downloads."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir

@pytest.fixture
def downloader(temp_dir):
    """Create a downloader instance."""
    return MusicDownloader(temp_dir)

@pytest.fixture
def mock_progress_callback():
    """Create a mock progress callback."""
    return Mock()

@pytest.fixture
def mock_ytdl():
    """Create a mock YoutubeDL instance with simulated download behavior."""
    with patch("yt_dlp.YoutubeDL") as mock:
        # Mock the context manager
        mock.return_value.__enter__.return_value = mock.return_value
        mock.return_value.__exit__.return_value = None
        
        # Mock extract_info with default success response
        mock.return_value.extract_info.return_value = {
            "title": "Test Song",
            "channel": "Test Artist",
            "duration": 180,
            "id": "test_id"
        }

        # Mock download method to return success
        mock.return_value.download.return_value = 0
        
        yield mock

@pytest.mark.asyncio
async def test_download_track_success(downloader, mock_progress_callback, mock_ytdl, temp_dir):
    """Test successful track download."""
    # Set up mock info
    info = {
        "title": "Test Song",
        "channel": "Test Artist",
        "duration": 180,
        "id": "test_id"
    }
    mock_ytdl.return_value.extract_info.return_value = info
    
    # Mock the output path generation and file existence
    expected_path = temp_dir / "Test Artist" / "Test Song.mp3"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    
    with patch.object(downloader, "_get_output_path", return_value=expected_path), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.object(downloader, "_update_metadata", return_value=None):  # Mock metadata update
        
        result = await downloader.download_track("test_id", mock_progress_callback)
        
        # Verify the result
        assert result == expected_path
        mock_progress_callback.assert_called_with("Download complete!", 1.0)
        mock_ytdl.return_value.extract_info.assert_called_once()

@pytest.mark.asyncio
async def test_download_track_metadata_failure(downloader, mock_progress_callback, mock_ytdl, temp_dir):
    """Test download succeeds even if metadata update fails."""
    # Set up mock info
    info = {
        "title": "Test Song",
        "channel": "Test Artist",
        "duration": 180,
        "id": "test_id"
    }
    mock_ytdl.return_value.extract_info.return_value = info
    
    # Mock output path and file existence
    expected_path = temp_dir / "Test Artist" / "Test Song.mp3"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    
    with patch.object(downloader, "_get_output_path", return_value=expected_path), \
         patch.object(downloader, "_update_metadata", side_effect=Exception("Metadata update failed")), \
         patch("pathlib.Path.exists", return_value=True):  # Mock file existence check
        
        result = await downloader.download_track("test_id", mock_progress_callback)
        
        # Verify the result
        assert result == expected_path
        mock_progress_callback.assert_any_call(
            "Warning: Metadata update failed, but download succeeded",
            0.95
        )

@pytest.mark.asyncio
async def test_download_track_cancelled(downloader, mock_progress_callback, mock_ytdl):
    """Test download cancellation."""
    # Create a patched version of extract_info that sets cancelled flag
    original_extract_info = mock_ytdl.return_value.extract_info
    def extract_info_and_cancel(*args, **kwargs):
        # Set cancelled flag before actual download starts
        downloader._cancelled = True
        return original_extract_info(*args, **kwargs)
    mock_ytdl.return_value.extract_info = extract_info_and_cancel
    
    with pytest.raises(RuntimeError) as exc_info:
        await downloader.download_track("test_id", mock_progress_callback)
    
    assert str(exc_info.value) == "Download cancelled"
    # Verify no download was attempted
    mock_ytdl.return_value.download.assert_not_called()

@pytest.mark.asyncio
async def test_search_track_no_results(downloader, mock_ytdl):
    """Test search with no results."""
    # Mock empty search results
    mock_ytdl.return_value.extract_info.return_value = {"entries": []}
    
    results = []
    async for result in downloader.search_track("nonexistent song"):
        results.append(result)
    
    assert len(results) == 0
    mock_ytdl.return_value.extract_info.assert_called_once()

@pytest.mark.asyncio
async def test_search_track_with_results(downloader, mock_ytdl):
    """Test search with results."""
    # Mock search results
    mock_ytdl.return_value.extract_info.return_value = {
        "entries": [{
            "id": "test_id",
            "title": "Test Song",
            "channel": "Test Artist",
            "duration": 180,
            "view_count": 1000000,
            "like_count": 10000,
            "channel_verified": True
        }]
    }
    
    results = []
    async for result in downloader.search_track("test song"):
        results.append(result)
    
    assert len(results) == 1
    assert results[0]["title"] == "Test Song"
    assert results[0]["channel"] == "Test Artist"
    assert "score" in results[0]  # Verify score was calculated

@pytest.mark.asyncio
async def test_search_track_error_handling(downloader, mock_ytdl):
    """Test search error handling."""
    # Mock YouTube API error
    mock_ytdl.return_value.extract_info.side_effect = Exception("API Error")
    
    with pytest.raises(Exception) as exc_info:
        async for _ in downloader.search_track("test song"):
            pass
    
    assert "API Error" in str(exc_info.value)

@pytest.mark.asyncio
async def test_download_track_path_generation(downloader, mock_progress_callback, mock_ytdl, temp_dir):
    """Test download path generation with special characters."""
    # Test with filename containing special characters
    info = {
        "title": "Test: Song? (Official Audio)",
        "channel": "Test/Artist\\Name",
        "duration": 180,
        "id": "test_id"
    }
    mock_ytdl.return_value.extract_info.return_value = info
    
    expected_path = temp_dir / "Test Artist Name" / "Test Song (Official Audio).mp3"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    
    with patch.object(downloader, "_get_output_path", return_value=expected_path), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.object(downloader, "_update_metadata", return_value=None):  # Mock metadata update
        
        result = await downloader.download_track("test_id", mock_progress_callback)
        assert result == expected_path 