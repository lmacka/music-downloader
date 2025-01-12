from pathlib import Path
from typing import Dict, Optional, cast
import uuid
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea,
    QSplitter, QFrame, QLabel, QLayout
)
from PySide6.QtCore import Qt
from .task_card import TaskCard

logger = logging.getLogger(__name__)

class TaskSection(QWidget):
    """Section for displaying task cards."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        
        # Set up layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self._layout.addWidget(title_label)
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)
        self._layout.addWidget(scroll)
        
        # Container for cards
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(5, 5, 5, 5)
        self.container_layout.setSpacing(5)
        self.container_layout.addStretch()
        
        scroll.setWidget(self.container)
        
    def add_card(self, card: TaskCard):
        """Add a card to this section."""
        # Remove from previous parent if needed
        if card.parent():
            parent_widget = cast(QWidget, card.parent())
            parent_layout = parent_widget.layout()
            if parent_layout and isinstance(parent_layout, QLayout):
                parent_layout.removeWidget(card)
            
        # Add to our layout before the stretch
        self.container_layout.insertWidget(self.container_layout.count() - 1, card)
        card.show()
        
    def remove_card(self, card: TaskCard):
        """Remove a card from this section."""
        self.container_layout.removeWidget(card)

class TaskManager(QWidget):
    """Widget for managing download tasks."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        # Active tasks section
        self.active_section = TaskSection("Active Downloads")
        splitter.addWidget(self.active_section)
        
        # Completed tasks section
        self.completed_section = TaskSection("Completed")
        splitter.addWidget(self.completed_section)
        
        # Set initial sizes
        splitter.setSizes([200, 100])  # 2:1 ratio
        
        # Track tasks
        self.tasks: Dict[str, TaskCard] = {}
        
    def create_task(self, title: str, artist: str) -> str:
        """Create a new task card and return its ID."""
        task_id = str(uuid.uuid4())
        logger.debug("Creating task %s: %s - %s", task_id, artist, title)
        
        # Create card
        card = TaskCard(task_id, title, artist)
        card.cancel.connect(lambda: self._on_cancel(task_id))
        card.retry.connect(lambda: self._on_retry(task_id))
        card.remove.connect(lambda: self._on_remove(task_id))
        
        # Add to active section
        self.active_section.add_card(card)
        
        # Store card
        self.tasks[task_id] = card
        
        return task_id
        
    def update_task(self, task_id: str, status: str, progress: float = 0):
        """Update a task's status and progress."""
        if task_id in self.tasks:
            logger.debug("Updating task %s: %s (%.1f%%)", 
                        task_id, status, progress * 100)
            card = self.tasks[task_id]
            card.set_status(status, progress)
            
    def complete_task(self, task_id: str, file_path: Optional[Path] = None, metadata: Optional[Dict[str, str]] = None):
        """Mark a task as completed and move it to completed section."""
        if task_id in self.tasks:
            logger.info("Completing task %s", task_id)
            card = self.tasks[task_id]
            card.set_completed(file_path, metadata)
            
            # Move to completed section
            self.active_section.remove_card(card)
            self.completed_section.add_card(card)
            
    def fail_task(self, task_id: str, error: str):
        """Mark a task as failed."""
        if task_id in self.tasks:
            logger.error("Task %s failed: %s", task_id, error)
            card = self.tasks[task_id]
            card.set_error(error)
            
    def _on_cancel(self, task_id: str):
        """Handle task cancellation."""
        logger.info("Cancelling task %s", task_id)
        if task_id in self.tasks:
            card = self.tasks[task_id]
            card.set_cancelled()
            
    def _on_retry(self, task_id: str):
        """Handle task retry."""
        logger.info("Retrying task %s", task_id)
        if task_id in self.tasks:
            card = self.tasks[task_id]
            card.set_status("Retrying...")
            
            # Move back to active section
            self.completed_section.remove_card(card)
            self.active_section.add_card(card)
            
    def _on_remove(self, task_id: str):
        """Handle task removal."""
        logger.info("Removing task %s", task_id)
        if task_id in self.tasks:
            card = self.tasks[task_id]
            
            # Remove from sections
            self.active_section.remove_card(card)
            self.completed_section.remove_card(card)
            
            # Delete card
            card.deleteLater()
            del self.tasks[task_id] 