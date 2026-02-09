"""File watcher for auto-detecting uploaded tax documents.

Monitors a directory for new tax forms and receipts, automatically
categorizing them by type. Supports both polling-based watching
and one-shot scanning.
"""

import os
import time
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field


SUPPORTED_EXTENSIONS = {
    '.pdf', '.csv', '.xlsx', '.xls',
    '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp',
}

# Keywords used to auto-categorize files by name
FORM_KEYWORDS: Dict[str, List[str]] = {
    'W-2': ['w2', 'w-2', 'wage'],
    '1099-INT': ['1099int', '1099-int', 'interest'],
    '1099-DIV': ['1099div', '1099-div', 'dividend'],
    '1099-NEC': ['1099nec', '1099-nec', 'nonemployee'],
    '1099-MISC': ['1099misc', '1099-misc', 'miscellaneous'],
    '1099-B': ['1099b', '1099-b', 'broker', 'brokerage'],
    '1099-R': ['1099r', '1099-r', 'retirement', 'distribution'],
    '1098': ['1098', 'mortgage'],
    'Schedule E': ['schedule-e', 'schedulee', 'rental'],
    'Receipt': ['receipt', 'expense'],
    'Vehicle Registration': ['vehicle', 'registration', 'dmv', 'vlf'],
    'Property Tax': ['property-tax', 'propertytax', 'real-estate-tax'],
    'Estimated Payment': ['estimated', 'voucher', '1040-es', '540-es'],
}


@dataclass
class DetectedFile:
    """A detected tax document file."""
    path: str
    filename: str
    extension: str
    category: Optional[str] = None  # Auto-detected category
    size_bytes: int = 0
    modified_time: float = 0.0


@dataclass
class WatcherState:
    """Internal state for the directory watcher."""
    known_files: Set[str] = field(default_factory=set)
    new_files: List[DetectedFile] = field(default_factory=list)


class TaxDocumentWatcher:
    """Watches a directory for new tax documents."""

    def __init__(
        self,
        watch_dir: str,
        callback: Optional[Callable[[DetectedFile], None]] = None,
        poll_interval: float = 2.0,
    ):
        """
        Initialize the file watcher.

        Args:
            watch_dir: Directory path to monitor.
            callback: Function called when a new file is detected.
            poll_interval: Seconds between directory scans.
        """
        self.watch_dir = Path(watch_dir)
        self.callback = callback
        self.poll_interval = poll_interval
        self._state = WatcherState()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _categorize_file(self, filename: str) -> Optional[str]:
        """
        Attempt to categorize a file based on its name.

        Args:
            filename: The filename (without path).

        Returns:
            Category string or None if unrecognized.
        """
        name_lower = filename.lower().replace(' ', '').replace('_', '')
        for category, keywords in FORM_KEYWORDS.items():
            for keyword in keywords:
                if keyword.replace('-', '') in name_lower:
                    return category
        return None

    def scan_directory(self) -> List[DetectedFile]:
        """
        Perform a one-shot scan of the watch directory.

        Returns:
            List of all supported files found.
        """
        if not self.watch_dir.exists():
            return []

        detected = []
        for file_path in self.watch_dir.rglob('*'):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            stat = file_path.stat()
            df = DetectedFile(
                path=str(file_path),
                filename=file_path.name,
                extension=file_path.suffix.lower(),
                category=self._categorize_file(file_path.name),
                size_bytes=stat.st_size,
                modified_time=stat.st_mtime,
            )
            detected.append(df)

        # Sort by modification time, newest first
        detected.sort(key=lambda f: f.modified_time, reverse=True)
        return detected

    def scan_for_new_files(self) -> List[DetectedFile]:
        """
        Scan for files not previously seen.

        Returns:
            List of newly detected files since last scan.
        """
        all_files = self.scan_directory()
        new_files = []
        for f in all_files:
            if f.path not in self._state.known_files:
                self._state.known_files.add(f.path)
                new_files.append(f)
                self._state.new_files.append(f)
        return new_files

    def _poll_loop(self):
        """Internal polling loop for the watcher thread."""
        # Initial scan to populate known files
        initial = self.scan_directory()
        for f in initial:
            self._state.known_files.add(f.path)

        while self._running:
            time.sleep(self.poll_interval)
            new_files = self.scan_for_new_files()
            for f in new_files:
                if self.callback:
                    self.callback(f)

    def start(self):
        """Start watching the directory in a background thread."""
        if self._running:
            return

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the directory watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def get_summary(self) -> Dict[str, List[DetectedFile]]:
        """
        Get a summary of all detected files grouped by category.

        Returns:
            Dictionary mapping category names to lists of files.
        """
        all_files = self.scan_directory()
        categorized: Dict[str, List[DetectedFile]] = {}
        for f in all_files:
            cat = f.category or "Uncategorized"
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(f)
        return categorized

    @staticmethod
    def print_summary(categorized: Dict[str, List[DetectedFile]]):
        """Print a formatted summary of detected files."""
        print("\n" + "=" * 50)
        print("  TAX DOCUMENT INVENTORY")
        print("=" * 50)

        total = 0
        for category, files in sorted(categorized.items()):
            print(f"\n  {category}:")
            for f in files:
                size_kb = f.size_bytes / 1024
                print(f"    - {f.filename} ({size_kb:.1f} KB)")
                total += 1

        print(f"\n  Total documents: {total}")
        print("=" * 50)
