# Add required assemblies
Add-Type -AssemblyName System.Web
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Suppress progress bars
$ProgressPreference = 'SilentlyContinue'

# Job state
$script:nextJobId = 1
$script:activeJobs = @{}
$script:jobQueue = New-Object System.Collections.Queue

# Constants
$MUSIC_DIR = Join-Path $PSScriptRoot "music"
$BIN_DIR = Join-Path $PSScriptRoot "bin"
$LIB_DIR = Join-Path $PSScriptRoot "lib"
$YT_DLP = Join-Path $BIN_DIR "yt-dlp.exe"
$FFMPEG = Join-Path $BIN_DIR "ffmpeg.exe"

# Load TagLib from lib directory
$tagLibPath = Join-Path $LIB_DIR "taglib-sharp.dll"
if (-not (Test-Path $tagLibPath)) {
    Write-Host "Error: TagLib# library not found at $tagLibPath"
    Write-Host "Please ensure taglib-sharp.dll is present in the lib directory"
    exit 1
}
Add-Type -Path $tagLibPath

# Function definitions
function Write-JobLog {
    param(
        [string]$Message,
        [string]$Level = 'INFO',
        [int]$JobId = 0
    )
    
    $timestamp = Get-Date -Format "HH:mm:ss"
    $jobPrefix = if ($JobId -gt 0) { "[$($JobId.ToString('00'))] " } else { "" }
    $logMessage = "$timestamp $jobPrefix$Message"
    
    # Update UI from the UI thread
    if ($script:logTextBox) {
        $script:form.Invoke([Action]{
            $script:logTextBox.AppendText("$logMessage`r`n")
            $script:logTextBox.SelectionStart = $script:logTextBox.TextLength
            $script:logTextBox.ScrollToCaret()
            # Force refresh
            $script:logTextBox.Refresh()
        })
    }
}

function Get-MusicBrainzMetadata {
    param(
        [string]$Artist,
        [string]$Title
    )
    
    try {
        Write-JobOutput "Searching MusicBrainz for: $Title by $Artist"
        
        # Create a web client with a proper user agent (required by MusicBrainz)
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "YouTubeMusicDownloader/1.0 ( brainz@lmacka.io )")
        $webClient.Headers.Add("Accept", "application/json")
        
        # Try different search strategies
        $queries = @(
            # If we have both artist and title, try that first
            if ($Artist -and $Title) {
                "artist:$Artist AND recording:$Title"
            }
            # Then try just the title (useful for well-known songs)
            "recording:$Title type:song"
        )
        
        foreach ($searchQuery in $queries) {
            Write-JobOutput "  Trying query: $searchQuery"
            
            # URL encode the search query
            $queryEncoded = [System.Web.HttpUtility]::UrlEncode($searchQuery)
            $url = "https://musicbrainz.org/ws/2/recording/?query=$queryEncoded&fmt=json&inc=genres+tags+releases+artists"
            
        $response = $webClient.DownloadString($url)
        $data = $response | ConvertFrom-Json
        
        if ($data.recordings.Count -gt 0) {
            $recording = $data.recordings[0]
            
            # Get the first release if available
                $release = if ($recording.releases.Count -gt 0) { 
                    # Prefer releases with dates
                    $recording.releases | Where-Object { $_.date } | Select-Object -First 1
                }
                if (-not $release -and $recording.releases.Count -gt 0) {
                    $release = $recording.releases[0]
                }
            
            # Try to get genre from recording tags or genres
            $genre = ""
            if ($recording.genres -and $recording.genres.Count -gt 0) {
                $genre = $recording.genres[0].name
                    Write-JobOutput "  Found genre from recording: $genre"
            }
            elseif ($recording.tags -and $recording.tags.Count -gt 0) {
                # Look for genre-like tags (filtering out non-genre tags)
                $genreTags = $recording.tags | Where-Object {
                    $_.name -notmatch '^\d+s$' -and  # Filter out decade tags
                    $_.name -notmatch '^(male|female) vocalists?$' -and  # Filter out vocalist tags
                    $_.name -notmatch '^(classic|favorite|beautiful|awesome)$'  # Filter out subjective tags
                }
                if ($genreTags) {
                    $genre = $genreTags[0].name
                        Write-JobOutput "  Found genre from tags: $genre"
                    }
                }
                
                # Get artist name
                $artist = if ($recording.'artist-credit'.Count -gt 0) {
                    $recording.'artist-credit'[0].name
                } elseif ($recording.artists.Count -gt 0) {
                    $recording.artists[0].name
                } else { "" }
                
                Write-JobOutput "  Found recording: $($recording.title) by $artist"
            
            return @{
                title = $recording.title
                    artist = $artist
                album = if ($release) { $release.title } else { "" }
                year = if ($release -and $release.date -match '^\d{4}') { $matches[0] } else { "" }
                genre = $genre
            }
        }
        }
        
        Write-JobOutput "No matching recording found in MusicBrainz"
    }
    catch {
        Write-JobOutput "MusicBrainz lookup failed: $($_.Exception.Message)"
    }
    
    # If we get here, try to construct basic metadata from the video title
    Write-JobOutput "Using basic metadata from video title"
    return @{
        title = $Title
        artist = $Artist
        album = ""
        year = ""
        genre = ""
    }
}

function Apply-Metadata {
    param(
        [string]$FilePath,
        [hashtable]$Metadata
    )
    
    try {
        $file = [TagLib.File]::Create($FilePath)
        
        Write-JobOutput "Applying metadata fields..."
        
        # Set basic properties
        if ($Metadata.title) {
            $file.Tag.Title = $Metadata.title
            Write-JobOutput "  Set title: $($Metadata.title)"
        }
        
        if ($Metadata.artist) {
            $file.Tag.Performers = @($Metadata.artist)
            Write-JobOutput "  Set artist: $($Metadata.artist)"
        }
        
        if ($Metadata.album) { 
            $file.Tag.Album = $Metadata.album 
            Write-JobOutput "  Set album: $($Metadata.album)"
        }
        
        if ($Metadata.year -and [int]::TryParse($Metadata.year, [ref]$null)) { 
            $file.Tag.Year = [int]$Metadata.year 
            Write-JobOutput "  Set year: $($Metadata.year)"
        }
        
        if ($Metadata.genre -and -not [string]::IsNullOrWhiteSpace($Metadata.genre)) { 
            Write-JobOutput "  Setting genre to: $($Metadata.genre)"
            $file.Tag.Genres = @($Metadata.genre)
        }
        
        # Save changes
        Write-JobOutput "Saving metadata changes..."
        $file.Save()
        
        # Verify metadata was written
        Write-JobOutput "Verifying metadata..."
        $verifyFile = [TagLib.File]::Create($FilePath)
        Write-JobOutput "Metadata verification:"
        Write-JobOutput "  Title: $($verifyFile.Tag.Title)"
        Write-JobOutput "  Artist: $($verifyFile.Tag.FirstPerformer)"
        if ($verifyFile.Tag.Album) { Write-JobOutput "  Album: $($verifyFile.Tag.Album)" }
        if ($verifyFile.Tag.Year -gt 0) { Write-JobOutput "  Year: $($verifyFile.Tag.Year)" }
        if ($verifyFile.Tag.FirstGenre) { Write-JobOutput "  Genre: $($verifyFile.Tag.FirstGenre)" }
        
        return $true
    }
    catch {
        Write-JobOutput "Metadata application failed: $($_.Exception.Message)"
        return $false
    }
}

function Start-MusicDownload {
    param([string]$Query)
    
    $jobId = $script:nextJobId++
    Write-JobLog "Starting download for: $Query" -JobId $jobId
    
    # Start the download job
    $job = Start-Job -ScriptBlock {
        param($query, $jobId, $ytDlp, $ffmpeg, $userMusicDir, $binDir, $tagLibPath)
        
        # Load TagLib
        Add-Type -Path $tagLibPath
        Add-Type -AssemblyName System.Web
        
        function Write-JobOutput {
            param($Message)
            "$jobId|$Message"
        }
        
        # Add USB drive detection function
        function Get-USBDrive {
            Get-WmiObject Win32_LogicalDisk | Where-Object { 
                $_.DriveType -eq 2 -and  # Removable drive
                (Test-Path "$($_.DeviceID)\") -and  # Drive is accessible
                $_.Size -gt 0  # Drive has storage
            } | Select-Object -First 1  # Get first available USB drive
        }
        
        # Add USB copy function
        function Copy-SongToUSB {
            param(
                [string]$FilePath,
                [string]$Artist,
                [string]$Title
            )
            
            if (-not $using:usbCopyEnabled) {
                Write-JobOutput "USB copy disabled, skipping"
                return
            }
            
            try {
                $usbDrive = Get-USBDrive
                if (-not $usbDrive) {
                    Write-JobOutput "No USB drive found"
                    return
                }
                
                # Create Music directory if it doesn't exist
                $musicPath = Join-Path $usbDrive.DeviceID "Music"
                if (-not (Test-Path $musicPath)) {
                    New-Item -ItemType Directory -Path $musicPath | Out-Null
                }
                
                # Create artist directory
                $artistPath = Join-Path $musicPath $Artist
                if (-not (Test-Path $artistPath)) {
                    New-Item -ItemType Directory -Path $artistPath | Out-Null
                }
                
                # Copy file
                $destPath = Join-Path $artistPath (Split-Path $FilePath -Leaf)
                Copy-Item -Path $FilePath -Destination $destPath -Force
                Write-JobOutput "Copied to USB: $destPath"
                
                # Send a message to increment the USB counter
                Write-JobOutput "USB_COPY_SUCCESS"
            }
            catch {
                Write-JobOutput "Failed to copy to USB: $($_.Exception.Message)"
            }
        }
        
        function Apply-Metadata {
            param(
                [string]$FilePath,
                [hashtable]$Metadata
            )
            
            try {
                $file = [TagLib.File]::Create($FilePath)
                
                Write-JobOutput "Applying metadata fields..."
                
                # Set basic properties
                if ($Metadata.title) {
                    $file.Tag.Title = $Metadata.title
                    Write-JobOutput "  Set title: $($Metadata.title)"
                }
                
                if ($Metadata.artist) {
                    $file.Tag.Performers = @($Metadata.artist)
                    Write-JobOutput "  Set artist: $($Metadata.artist)"
                }
                
                if ($Metadata.album) { 
                    $file.Tag.Album = $Metadata.album 
                    Write-JobOutput "  Set album: $($Metadata.album)"
                }
                
                if ($Metadata.year -and [int]::TryParse($Metadata.year, [ref]$null)) { 
                    $file.Tag.Year = [int]$Metadata.year 
                    Write-JobOutput "  Set year: $($Metadata.year)"
                }
                
                if ($Metadata.genre -and -not [string]::IsNullOrWhiteSpace($Metadata.genre)) { 
                    Write-JobOutput "  Setting genre to: $($Metadata.genre)"
                    $file.Tag.Genres = @($Metadata.genre)
                }
                
                # Save changes
                Write-JobOutput "Saving metadata changes..."
                $file.Save()
                
                # Verify metadata was written
                Write-JobOutput "Verifying metadata..."
                $verifyFile = [TagLib.File]::Create($FilePath)
                Write-JobOutput "Metadata verification:"
                Write-JobOutput "  Title: $($verifyFile.Tag.Title)"
                Write-JobOutput "  Artist: $($verifyFile.Tag.FirstPerformer)"
                if ($verifyFile.Tag.Album) { Write-JobOutput "  Album: $($verifyFile.Tag.Album)" }
                if ($verifyFile.Tag.Year -gt 0) { Write-JobOutput "  Year: $($verifyFile.Tag.Year)" }
                if ($verifyFile.Tag.FirstGenre) { Write-JobOutput "  Genre: $($verifyFile.Tag.FirstGenre)" }
                
                return $true
            }
            catch {
                Write-JobOutput "Metadata application failed: $($_.Exception.Message)"
                return $false
            }
        }
        
        function Get-MusicBrainzMetadata {
            param(
                [string]$Artist,
                [string]$Title
            )
            
            try {
                # Create a web client with a proper user agent (required by MusicBrainz)
                $webClient = New-Object System.Net.WebClient
                $webClient.Headers.Add("User-Agent", "YouTubeMusicDownloader/1.0 ( brainz@lmacka.io )")
                $webClient.Headers.Add("Accept", "application/json")
                
                # URL encode the search terms
                $artistEncoded = [System.Web.HttpUtility]::UrlEncode($Artist)
                $titleEncoded = [System.Web.HttpUtility]::UrlEncode($Title)
                
                # Query MusicBrainz
                $url = "https://musicbrainz.org/ws/2/recording/?query=artist:$artistEncoded AND recording:$titleEncoded&fmt=json&inc=genres+tags"
                $response = $webClient.DownloadString($url)
                $data = $response | ConvertFrom-Json
                
                if ($data.recordings.Count -gt 0) {
                    $recording = $data.recordings[0]
                    
                    # Get the first release if available
                    $release = if ($recording.releases.Count -gt 0) { $recording.releases[0] } else { $null }
                    
                    # Try to get genre from recording tags or genres
                    $genre = ""
                    if ($recording.genres -and $recording.genres.Count -gt 0) {
                        $genre = $recording.genres[0].name
                        Write-JobOutput "Found genre from recording: $genre"
                    }
                    elseif ($recording.tags -and $recording.tags.Count -gt 0) {
                        # Look for genre-like tags (filtering out non-genre tags)
                        $genreTags = $recording.tags | Where-Object {
                            $_.name -notmatch '^\d+s$' -and  # Filter out decade tags
                            $_.name -notmatch '^(male|female) vocalists?$' -and  # Filter out vocalist tags
                            $_.name -notmatch '^(classic|favorite|beautiful|awesome)$'  # Filter out subjective tags
                        }
                        if ($genreTags) {
                            $genre = $genreTags[0].name
                            Write-JobOutput "Found genre from tags: $genre"
                        }
                    }
                    
                    return @{
                        title = $recording.title
                        artist = $recording.'artist-credit'[0].name
                        album = if ($release) { $release.title } else { "" }
                        year = if ($release -and $release.date -match '^\d{4}') { $matches[0] } else { "" }
                        genre = $genre
                    }
                }
            }
            catch {
                Write-JobOutput "MusicBrainz lookup failed: $($_.Exception.Message)"
            }
            
            return $null
        }
        
        try {
            Write-JobOutput "Searching YouTube Music..."
            
            # Search for videos
            $searchArgs = @(
                "ytsearch10:$query",
                "--print", "%(id)s|%(title)s|%(duration)s|%(view_count)s|%(channel)s|%(like_count)s|%(uploader)s",
                "--flat-playlist",
                "--no-warnings",
                "--force-ipv4"
            )
            
            $results = & $ytDlp $searchArgs 2>&1
            if (-not $results) { throw "No results found" }
            
            # Score and select best match
            $bestMatch = $null
            $bestScore = -999
            
            $results | ForEach-Object {
                try {
                    $parts = $_ -split '\|'
                    if ($parts.Count -ge 6) {
                        $id = $parts[0]
                        $title = $parts[1]
                        $duration = if ([int]::TryParse($parts[2], [ref]$null)) { [int]$parts[2] } else { 0 }
                        $viewCount = if ($parts[3] -match '\d+') { [long]($matches[0]) } else { 0 }
                        $channel = $parts[4]
                        $likeCount = if ($parts[5] -match '\d+') { [long]($matches[0]) } else { 0 }
                        $uploader = if ($parts.Count -gt 6) { $parts[6] } else { "" }
                        
                        # Clean up title and channel for matching
                        $cleanTitle = $title -replace '[^\x20-\x7E]', ''  # Remove non-ASCII chars
                        $cleanChannel = $channel -replace '[^\x20-\x7E]', ''  # Remove non-ASCII chars
                        
                        # Parse search query
                        $searchArtist = ""
                        $searchTitle = $query
                        if ($query -match '^(.+?)\s+(?:-|\b)\s*(.+?)$') {
                            $searchArtist = $matches[1].Trim()
                            $searchTitle = $matches[2].Trim()
                        }
                        
                        # Parse video title
                        $videoArtist = ""
                        $videoTitle = $cleanTitle
                        if ($cleanTitle -match '^(.+?)\s*[-–]\s*(.+?)(?:\s*[\(\[].+)?$') {
                            $videoArtist = $matches[1].Trim()
                            $videoTitle = $matches[2].Trim()
                        }
                        
                        $score = 0
                        
                        # Exact match scoring (highest priority)
                        if ($searchArtist -and $videoArtist) {
                            if ($videoArtist -match [regex]::Escape($searchArtist)) { $score += 20 }
                        }
                        if ($videoTitle -match [regex]::Escape($searchTitle)) { $score += 20 }
                        
                        # Title word matching
                        $searchWords = $searchTitle -split '\s+'
                        $titleWords = $videoTitle -split '\s+'
                        $matchCount = $searchWords | Where-Object { $titleWords -contains $_ } | Measure-Object | Select-Object -ExpandProperty Count
                        $score += $matchCount * 5
                        
                        # Duration scoring (typical song length)
                        if ($duration -ge 180 -and $duration -lt 360) { $score += 3 }  # 3-6 minutes
                        elseif ($duration -ge 120 -and $duration -lt 480) { $score += 2 }  # 2-8 minutes
                        else { $score -= 3 }  # Too short or too long
                        
                        # Title format scoring
                        if ($cleanTitle -match '(?i)(official\s+(?:audio|video|music\s+video))') { $score += 5 }
                        if ($cleanTitle -match '(?i)(audio|lyrics|visualizer)') { $score += 3 }
                        if ($cleanTitle -match '(?i)(live|concert|performance|cover|remix|instrumental|karaoke)') { $score -= 10 }
                        if ($cleanTitle -match '(?i)(reaction|review|tutorial|how to|lesson)') { $score -= 15 }
                        if ($cleanTitle -match '(?i)(full\s+album|greatest\s+hits|compilation|mix)') { $score -= 20 }
                        
                        # Channel scoring
                        if ($cleanChannel -match [regex]::Escape($searchArtist)) { $score += 10 }
                        if ($cleanChannel -match '(?i)(vevo|official)') { $score += 5 }
                        if ($cleanChannel -match '(?i)(music|records|entertainment)') { $score += 2 }
                        
                        # Popularity scoring (log scale to prevent domination)
                        if ($viewCount -gt 1000000) { 
                            $score += [Math]::Min([Math]::Log10($viewCount) - 5, 5) 
                        }
                        if ($likeCount -gt 10000) { 
                            $score += [Math]::Min([Math]::Log10($likeCount) - 3, 3)
                        }
                        
                        Write-JobOutput "  Scored ($score): $title"
                        Write-JobOutput "    Artist Match: $videoArtist -> $searchArtist"
                        Write-JobOutput "    Title Match: $videoTitle -> $searchTitle"
                        
                        if ($score -gt $bestScore) {
                            $bestScore = $score
                            $bestMatch = @{
                                id = $id
                                title = $title
                                channel = $channel
                                uploader = $uploader
                            }
                        }
                    }
                } catch {
                    Write-JobOutput "Warning: Skipped result due to parsing error"
                }
            }
            
            if (-not $bestMatch -or $bestScore -lt 0) {
                throw "No suitable music track found"
            }
            
            Write-JobOutput "Selected: $($bestMatch.title)"
            Write-JobOutput "Channel: $($bestMatch.channel)"
            Write-JobOutput "Score: $bestScore"
            Write-JobOutput "Downloading..."
            
            # Download the track
            $ytDlpArgs = @(
                "https://youtube.com/watch?v=$($bestMatch.id)",
                "-x",
                "--audio-format", "mp3",
                "--output-na-placeholder", "_",
                "--restrict-filenames",
                "-o", "%(title).200s.%(ext)s",  # Temporary filename
                "--no-playlist",
                "--ffmpeg-location", $binDir,
                "--force-overwrites",
                "--print", "after_move:filepath",
                "--quiet"
            )
            
            $dlOutput = & $ytDlp $ytDlpArgs 2>&1
            if (-not $dlOutput -or $LASTEXITCODE -ne 0) {
                throw "Download failed"
            }
            
            $tempFilePath = $dlOutput | Select-String -Pattern "^.*\.mp3$" | Select-Object -Last 1
            if (-not (Test-Path $tempFilePath)) {
                throw "File not found after download"
            }
            
            # Parse artist and title from video title
            $title = $bestMatch.title
            $artist = ""
            $songTitle = $title
            
            if ($title -match '^(.+?)\s*[-–]\s*(.+?)(?:\s*[\(\[].+)?$') {
                $artist = $matches[1].Trim()
                $songTitle = $matches[2].Trim()
            }
            
            Write-JobOutput "Looking up metadata..."
            $metadata = Get-MusicBrainzMetadata -Artist $artist -Title $songTitle
            
            if (-not $metadata) {
                Write-JobOutput "Using basic metadata from video title"
                $metadata = @{
                    title = $songTitle
                    artist = $artist
                    album = ""
                    year = ""
                    genre = ""
                }
            }
            
            # Create artist directory in user's music folder
            $artistDir = Join-Path $userMusicDir $metadata.artist
            if (-not (Test-Path $artistDir)) {
                New-Item -ItemType Directory -Path $artistDir | Out-Null
            }
            
            # Move file to artist directory with clean name
            $cleanTitle = $metadata.title -replace '[^\w\s-]', '' -replace '\s+', '_'
            $finalFilePath = Join-Path $artistDir "$cleanTitle.mp3"
            Move-Item -Path $tempFilePath -Destination $finalFilePath -Force
            
            Write-JobOutput "Found metadata:"
            Write-JobOutput "  Title: $($metadata.title)"
            Write-JobOutput "  Artist: $($metadata.artist)"
            if ($metadata.album) { Write-JobOutput "  Album: $($metadata.album)" }
            if ($metadata.year) { Write-JobOutput "  Year: $($metadata.year)" }
            if ($metadata.genre) { Write-JobOutput "  Genre: $($metadata.genre)" }
            
            Write-JobOutput "Applying metadata..."
            if (Apply-Metadata -FilePath $finalFilePath -Metadata $metadata) {
                $file = Get-Item $finalFilePath
                $fileSize = [math]::Round($file.Length / 1MB, 1)
                Write-JobOutput "Saved: $($metadata.artist)/$($file.Name) (${fileSize}MB)"
                
                # Try to copy to USB if artist is available
                if ($metadata.artist) {
                    Write-JobOutput "Checking for USB drive..."
                    Copy-SongToUSB -FilePath $finalFilePath -Artist $metadata.artist -Title $metadata.title
                }
            } else {
                throw "Failed to apply metadata"
            }
            
        } catch {
            Write-JobOutput "Error: $($_.Exception.Message)"
        }
    } -ArgumentList $Query, $jobId, $YT_DLP, $FFMPEG, $USER_MUSIC_DIR, $BIN_DIR, $tagLibPath
    
    $script:activeJobs[$jobId] = @{
        Id = $jobId
        Job = $job
        Query = $Query
    }
}

# Create the main form
$script:form = New-Object System.Windows.Forms.Form
$script:form.Text = "YouTube Music Downloader"
$script:form.Size = New-Object System.Drawing.Size(800, 600)
$script:form.StartPosition = "CenterScreen"
$script:form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

# Create welcome label
$welcomeLabel = New-Object System.Windows.Forms.Label
$welcomeLabel.Location = New-Object System.Drawing.Point(10, 10)
$welcomeLabel.Size = New-Object System.Drawing.Size(760, 20)
$welcomeLabel.Text = "Enter song name/artist to download:"
$welcomeLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$script:form.Controls.Add($welcomeLabel)

# Create search box
$searchBox = New-Object System.Windows.Forms.TextBox
$searchBox.Location = New-Object System.Drawing.Point(10, 35)
$searchBox.Size = New-Object System.Drawing.Size(660, 20)
$searchBox.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$script:form.Controls.Add($searchBox)

# Create download button
$downloadButton = New-Object System.Windows.Forms.Button
$downloadButton.Location = New-Object System.Drawing.Point(680, 33)
$downloadButton.Size = New-Object System.Drawing.Size(90, 25)
$downloadButton.Text = "Download"
$downloadButton.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$script:form.Controls.Add($downloadButton)

# Create job stats panel
$jobStatsPanel = New-Object System.Windows.Forms.Panel
$jobStatsPanel.Location = New-Object System.Drawing.Point(10, 65)
$jobStatsPanel.Size = New-Object System.Drawing.Size(760, 25)
$jobStatsPanel.BackColor = [System.Drawing.Color]::FromArgb(240, 240, 240)
$script:form.Controls.Add($jobStatsPanel)

# Add USB copy checkbox
$script:usbCopyEnabled = $true  # Default to enabled
$usbCheckbox = New-Object System.Windows.Forms.CheckBox
$usbCheckbox.Location = New-Object System.Drawing.Point(680, 5)
$usbCheckbox.Size = New-Object System.Drawing.Size(150, 20)
$usbCheckbox.Text = "Copy to USB"
$usbCheckbox.Checked = $true
$usbCheckbox.Add_CheckedChanged({
    $script:usbCopyEnabled = $usbCheckbox.Checked
})
$jobStatsPanel.Controls.Add($usbCheckbox)

# Job stats labels
$script:jobStats = @{
    Completed = 0
    Failed = 0
    USBCopied = 0
}

$statsLabel = New-Object System.Windows.Forms.Label
$statsLabel.Location = New-Object System.Drawing.Point(10, 5)
$statsLabel.Size = New-Object System.Drawing.Size(50, 15)
$statsLabel.Text = "Jobs:"
$statsLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$jobStatsPanel.Controls.Add($statsLabel)

$script:queuedLabel = New-Object System.Windows.Forms.Label
$script:queuedLabel.Location = New-Object System.Drawing.Point(60, 5)
$script:queuedLabel.Size = New-Object System.Drawing.Size(100, 15)
$script:queuedLabel.Text = "Queued: 0"
$jobStatsPanel.Controls.Add($script:queuedLabel)

$script:runningLabel = New-Object System.Windows.Forms.Label
$script:runningLabel.Location = New-Object System.Drawing.Point(170, 5)
$script:runningLabel.Size = New-Object System.Drawing.Size(100, 15)
$script:runningLabel.Text = "Running: 0"
$jobStatsPanel.Controls.Add($script:runningLabel)

$script:completedLabel = New-Object System.Windows.Forms.Label
$script:completedLabel.Location = New-Object System.Drawing.Point(280, 5)
$script:completedLabel.Size = New-Object System.Drawing.Size(100, 15)
$script:completedLabel.Text = "Completed: 0"
$jobStatsPanel.Controls.Add($script:completedLabel)

$script:failedLabel = New-Object System.Windows.Forms.Label
$script:failedLabel.Location = New-Object System.Drawing.Point(390, 5)
$script:failedLabel.Size = New-Object System.Drawing.Size(100, 15)
$script:failedLabel.Text = "Failed: 0"
$jobStatsPanel.Controls.Add($script:failedLabel)

$script:usbCopiedLabel = New-Object System.Windows.Forms.Label
$script:usbCopiedLabel.Location = New-Object System.Drawing.Point(500, 5)
$script:usbCopiedLabel.Size = New-Object System.Drawing.Size(100, 15)
$script:usbCopiedLabel.Text = "USB Copied: 0"
$jobStatsPanel.Controls.Add($script:usbCopiedLabel)

# Create log view
$script:logTextBox = New-Object System.Windows.Forms.RichTextBox
$script:logTextBox.Location = New-Object System.Drawing.Point(10, 100)
$script:logTextBox.Size = New-Object System.Drawing.Size(760, 450)
$script:logTextBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$script:logTextBox.Multiline = $true
$script:logTextBox.ReadOnly = $true
$script:logTextBox.BackColor = [System.Drawing.Color]::White
$script:logTextBox.ScrollBars = "Vertical"
$script:form.Controls.Add($script:logTextBox)

# Function to update job stats
function Update-JobStats {
    if (-not $script:form -or -not $script:form.IsHandleCreated) { return }
    
    $script:form.Invoke([Action]{
        $script:queuedLabel.Text = "Queued: $($script:jobQueue.Count)"
        $script:runningLabel.Text = "Running: $($script:activeJobs.Count)"
        $script:completedLabel.Text = "Completed: $($script:jobStats.Completed)"
        $script:failedLabel.Text = "Failed: $($script:jobStats.Failed)"
        $script:usbCopiedLabel.Text = "USB Copied: $($script:jobStats.USBCopied)"
        
        # Update colors based on status
        $script:queuedLabel.ForeColor = if ($script:jobQueue.Count -gt 0) { [System.Drawing.Color]::Blue } else { [System.Drawing.Color]::Black }
        $script:runningLabel.ForeColor = if ($script:activeJobs.Count -gt 0) { [System.Drawing.Color]::Green } else { [System.Drawing.Color]::Black }
        $script:failedLabel.ForeColor = if ($script:jobStats.Failed -gt 0) { [System.Drawing.Color]::Red } else { [System.Drawing.Color]::Black }
        $script:usbCopiedLabel.ForeColor = if ($script:jobStats.USBCopied -gt 0) { [System.Drawing.Color]::DarkGreen } else { [System.Drawing.Color]::Black }
    })
}

# Modify job timer to update stats
$jobTimer = New-Object System.Windows.Forms.Timer
$jobTimer.Interval = 100
$jobTimer.Add_Tick({
    # Check for completed jobs
    foreach ($jobId in @($script:activeJobs.Keys)) {
        $jobInfo = $script:activeJobs[$jobId]
        if ($jobInfo.Job.State -ne 'Running') {
            $output = Receive-Job -Job $jobInfo.Job
            $hasError = $false
            if ($output) {
                foreach ($line in $output) {
                    if ($line -match '^\d+\|(.+)$') {
                        $message = $matches[1]
                        Write-JobLog $message -JobId $jobId
                        if ($message -match '^Error:') {
                            $hasError = $true
                        }
                        # Check for USB copy success message
                        if ($message -eq 'USB_COPY_SUCCESS') {
                            $script:jobStats.USBCopied++
                            Update-JobStats
                        }
                    }
                }
            }
            
            # Clean up job
            Remove-Job -Job $jobInfo.Job -Force
            $script:activeJobs.Remove($jobId)
            
            # Update stats
            if ($hasError) {
                $script:jobStats.Failed++
            } else {
                $script:jobStats.Completed++
            }
            
            Write-JobLog "Job finished" -JobId $jobId
            
            # Start next job if any in queue
            if ($script:jobQueue.Count -gt 0) {
                $nextQuery = $script:jobQueue.Dequeue()
                Start-MusicDownload $nextQuery
            }
            
            Update-JobStats
        }
    }
})
$jobTimer.Start()

# Get user name
$userName = ""
$nameForm = New-Object System.Windows.Forms.Form
$nameForm.Text = "Enter Your Name"
$nameForm.Size = New-Object System.Drawing.Size(300, 150)
$nameForm.StartPosition = "CenterScreen"
$nameForm.FormBorderStyle = "FixedDialog"
$nameForm.MaximizeBox = $false
$nameForm.MinimizeBox = $false

$nameLabel = New-Object System.Windows.Forms.Label
$nameLabel.Location = New-Object System.Drawing.Point(10, 20)
$nameLabel.Size = New-Object System.Drawing.Size(260, 20)
$nameLabel.Text = "Enter your name (letters only):"
$nameForm.Controls.Add($nameLabel)

$nameBox = New-Object System.Windows.Forms.TextBox
$nameBox.Location = New-Object System.Drawing.Point(10, 40)
$nameBox.Size = New-Object System.Drawing.Size(260, 20)
$nameForm.Controls.Add($nameBox)

$okButton = New-Object System.Windows.Forms.Button
$okButton.Location = New-Object System.Drawing.Point(100, 70)
$okButton.Size = New-Object System.Drawing.Size(75, 23)
$okButton.Text = "OK"
$okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$nameForm.Controls.Add($okButton)
$nameForm.AcceptButton = $okButton

do {
    $result = $nameForm.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $userName = $nameBox.Text.Trim()
    }
} while ($result -eq [System.Windows.Forms.DialogResult]::OK -and -not ($userName -match '^[a-zA-Z]+$'))

# Capitalize first letter, lowercase rest
$userName = $userName.Substring(0,1).ToUpper() + $userName.Substring(1).ToLower()

# Update music directory to include user name
$USER_MUSIC_DIR = Join-Path $MUSIC_DIR $userName

# Ensure directories exist
if (-not (Test-Path $MUSIC_DIR)) { New-Item -ItemType Directory -Path $MUSIC_DIR | Out-Null }
if (-not (Test-Path $USER_MUSIC_DIR)) { New-Item -ItemType Directory -Path $USER_MUSIC_DIR | Out-Null }

# Update welcome message
$welcomeLabel.Text = "Welcome, $userName! Enter song name/artist to download:"

# Reset job stats
$script:jobStats = @{
    Completed = 0
    Failed = 0
    USBCopied = 0
}

# Modify download button click
$downloadButton.Add_Click({
    $query = $searchBox.Text.Trim()
    if ($query) {
        # Clear search box
        $searchBox.Clear()
        
        if ($script:activeJobs.Count -eq 0) {
            # Start immediately if no active jobs
            Start-MusicDownload $query
        } else {
            # Queue the download
            $script:jobQueue.Enqueue($query)
            Write-JobLog "Queued download: $query"
        }
        
        Update-JobStats
        $searchBox.Focus()  # Return focus to search box
    }
})

# Handle Enter key in search box
$searchBox.Add_KeyDown({
    param($sender, $e)
    if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
        $downloadButton.PerformClick()
        $e.SuppressKeyPress = $true
    }
})

# Show the form
$script:form.Add_Shown({
    $script:form.Activate()
    Update-JobStats
})

# Add function to detect USB drives
function Get-USBDrive {
    Get-WmiObject Win32_LogicalDisk | Where-Object { 
        $_.DriveType -eq 2 -and  # Removable drive
        (Test-Path "$($_.DeviceID)\") -and  # Drive is accessible
        $_.Size -gt 0  # Drive has storage
    } | Select-Object -First 1  # Get first available USB drive
}

# Add function to copy song to USB drive
function Copy-SongToUSB {
    param(
        [string]$FilePath,
        [string]$Artist,
        [string]$Title
    )
    
    if (-not $script:usbCopyEnabled) {
        Write-JobOutput "USB copy disabled, skipping"
        return
    }
    
    try {
        $usbDrive = Get-USBDrive
        if (-not $usbDrive) {
            Write-JobOutput "No USB drive found"
            return
        }
        
        # Create Music directory if it doesn't exist
        $musicPath = Join-Path $usbDrive.DeviceID "Music"
        if (-not (Test-Path $musicPath)) {
            New-Item -ItemType Directory -Path $musicPath | Out-Null
        }
        
        # Create artist directory
        $artistPath = Join-Path $musicPath $Artist
        if (-not (Test-Path $artistPath)) {
            New-Item -ItemType Directory -Path $artistPath | Out-Null
        }
        
        # Copy file
        $destPath = Join-Path $artistPath (Split-Path $FilePath -Leaf)
        Copy-Item -Path $FilePath -Destination $destPath -Force
        Write-JobOutput "Copied to USB: $destPath"
        
        # Send a message to increment the USB counter
        Write-JobOutput "USB_COPY_SUCCESS"
    }
    catch {
        Write-JobOutput "Failed to copy to USB: $($_.Exception.Message)"
    }
}

# Add function to safely eject USB drive
function Eject-USBDrive {
    param([string]$DriveLetter)
    
    try {
        $driveEject = New-Object -ComObject Shell.Application
        $driveEject.Namespace(17).ParseName($DriveLetter).InvokeVerb("Eject")
        return $true
    }
    catch {
        return $false
    }
}

# Add form closing handler
$script:form.Add_FormClosing({
    param($sender, $e)
    
    $usbDrive = Get-USBDrive
    if ($usbDrive) {
        $result = [System.Windows.Forms.MessageBox]::Show(
            "Would you like to safely eject the USB drive ($($usbDrive.DeviceID))?",
            "Eject USB Drive?",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        
        if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
            Write-Host "Ejecting USB drive..."
            if (Eject-USBDrive -DriveLetter $usbDrive.DeviceID) {
                [System.Windows.Forms.MessageBox]::Show(
                    "USB drive ejected successfully.",
                    "Success",
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    [System.Windows.Forms.MessageBoxIcon]::Information
                )
            } else {
                [System.Windows.Forms.MessageBox]::Show(
                    "Failed to eject USB drive. Please eject manually.",
                    "Error",
                    [System.Windows.Forms.MessageBoxButtons]::OK,
                    [System.Windows.Forms.MessageBoxIcon]::Warning
                )
            }
        }
    }
})

[System.Windows.Forms.Application]::Run($script:form) 