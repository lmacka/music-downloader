import re
from pathlib import Path
import logging
from better_profanity import profanity

logger = logging.getLogger(__name__)

class ContentFilter:
    """Filter content for profanity and clean filenames."""
    
    def __init__(self):
        """Initialize the content filter."""
        self.enabled = True
        # Initialize profanity filter with default wordlist
        profanity.load_censor_words()
        
    def contains_profanity(self, text: str) -> bool:
        """Check if text contains profanity."""
        if not self.enabled:
            return False
        return profanity.contains_profanity(text)
        
    def clean_filename(self, filename: str) -> str:
        """Clean a filename of invalid characters and profanity."""
        # Remove invalid filename characters
        clean = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        # Replace profanity with asterisks if enabled
        if self.enabled:
            clean = profanity.censor(clean)
            
        return clean.strip() 