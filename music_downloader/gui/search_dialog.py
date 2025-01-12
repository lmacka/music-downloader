from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QLabel
)
from PySide6.QtCore import Qt, Signal
from typing import List, Dict

class SearchResultsDialog(QDialog):
    """Dialog for displaying search results and selecting a track to download."""
    
    # Signal emitted when a track is selected
    track_selected = Signal(dict)  # Emits the selected track info
    
    def __init__(self, results: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Results")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Add instructions
        instructions = QLabel("Select a track to download:")
        layout.addWidget(instructions)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Title", "Channel", "Duration"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        
        # Add results to table
        self.table.setRowCount(len(results))
        self.results = results
        
        for i, result in enumerate(results):
            # Title
            title_item = QTableWidgetItem(result['title'])
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, title_item)
            
            # Channel
            channel_item = QTableWidgetItem(result.get('channel', ''))
            channel_item.setFlags(channel_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 1, channel_item)
            
            # Duration
            duration = result.get('duration', 0)
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            duration_text = f"{minutes}:{seconds:02d}"
            duration_item = QTableWidgetItem(duration_text)
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, duration_item)
        
        layout.addWidget(self.table)
        
        # Add buttons
        button_layout = QVBoxLayout()
        
        download_button = QPushButton("Download Selected")
        download_button.clicked.connect(self._on_download)
        button_layout.addWidget(download_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Select first row by default
        if results:
            self.table.selectRow(0)
    
    def _on_download(self):
        """Handle download button click."""
        selected_rows = self.table.selectedIndexes()
        if selected_rows:
            row = selected_rows[0].row()
            self.track_selected.emit(self.results[row])
            self.accept()
    
    def _on_double_click(self, item):
        """Handle double click on table item."""
        row = item.row()
        self.track_selected.emit(self.results[row])
        self.accept() 