"""File watcher for auto-detecting uploaded tax documents.

Monitors a directory for new tax forms and receipts, automatically
categorizing them by type. Supports both polling-based watching
and one-shot scanning.

Categorization priority:
  1. Parent folder path segments (deepest match first)
  2. Filename keyword matching (fallback)
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

# Map folder names (lowered) to document categories.
# Checked deepest-first against the relative path segments.
FOLDER_CATEGORY_MAP: Dict[str, str] = {
    'w2': 'W-2',
    '1098': '1098',
    '1099': '1099',
    'bank': '1099-INT',
    'brokers': '1099-B',
    'ira_retirement': '1099-R',
    '529': '529 Plan',
    'car_registration': 'Vehicle Registration',
    'car registration': 'Vehicle Registration',
    'estimated tax receipts': 'Estimated Payment',
    'estimated tax paid': 'Estimated Payment',
    'fsa': 'FSA',
    'home insurance': 'Home Insurance',
    'property tax': 'Property Tax',
    'rental': 'Schedule E',
    'donation': 'Charitable Contribution',
    'donations': 'Charitable Contribution',
}

# Keywords used to auto-categorize files by name (fallback)
FORM_KEYWORDS: Dict[str, List[str]] = {
    'W-2': ['w2', 'w-2', 'wage'],
    '1099-INT': ['1099int', '1099-int', 'interest'],
    '1099-DIV': ['1099div', '1099-div', 'dividend'],
    '1099-NEC': ['1099nec', '1099-nec', 'nonemployee'],
    '1099-MISC': ['1099misc', '1099-misc', 'miscellaneous'],
    '1099-B': ['1099b', '1099-b', 'broker', 'brokerage'],
    '1099-R': ['1099r', '1099-r', 'retirement', 'distribution'],
    '1099-G': ['1099g', '1099-g'],
    '1098': ['1098', 'mortgage'],
    '1098-T': ['1098t', '1098-t'],
    'Schedule E': ['schedule-e', 'schedulee', 'rental'],
    'Receipt': ['receipt', 'expense'],
    'Vehicle Registration': ['vehicle', 'registration', 'dmv', 'vlf'],
    'Property Tax': ['property-tax', 'propertytax', 'real-estate-tax'],
    'Estimated Payment': ['estimated', 'voucher', '1040-es', '540-es'],
    'Charitable Contribution': ['donation', 'charitable'],
}

# Categories where we can auto-extract structured data
EXTRACTABLE_CATEGORIES: Set[str] = {
    'W-2', '1099-INT', '1099-DIV', '1099-NEC', '1099-MISC',
    '1099-R', '1098',
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

    # ------------------------------------------------------------------
    # Categorization
    # ------------------------------------------------------------------

    def _categorize_file(self, file_path: Path) -> Optional[str]:
        """
        Categorize a file using folder structure first, then filename.

        Folder segments are checked deepest-first against
        FOLDER_CATEGORY_MAP.  If a match is found, special refinement
        is applied (e.g. 1098-T inside the 1098 folder, or 1099-G
        inside the 1099 folder).  Falls back to filename keyword
        matching.

        Args:
            file_path: Absolute path of the file.

        Returns:
            Category string or None if unrecognized.
        """
        # Compute path segments relative to the watch directory
        try:
            rel = file_path.relative_to(self.watch_dir)
        except ValueError:
            rel = file_path

        # Walk parent segments deepest-first (exclude the filename itself)
        parts = [p.lower() for p in rel.parts[:-1]]
        for segment in reversed(parts):
            if segment in FOLDER_CATEGORY_MAP:
                category = FOLDER_CATEGORY_MAP[segment]
                # Refine within 1098 folder
                if category == '1098':
                    category = self._refine_1098_from_filename(file_path.name, category)
                # Refine within 1099 folder
                if category == '1099':
                    category = self._refine_1099_from_filename(file_path.name) or '1099'
                return category

        # Fallback: filename-based keyword matching
        return self._categorize_by_filename(file_path.name)

    @staticmethod
    def _refine_1099_from_filename(filename: str) -> Optional[str]:
        """Refine 1099 sub-type from the filename for files directly in a 1099/ folder."""
        name_lower = filename.lower().replace(' ', '').replace('_', '')
        if '1099-g' in name_lower or '1099g' in name_lower:
            return '1099-G'
        if '1099-int' in name_lower or '1099int' in name_lower:
            return '1099-INT'
        if '1099-div' in name_lower or '1099div' in name_lower:
            return '1099-DIV'
        if '1099-r' in name_lower or '1099r' in name_lower:
            return '1099-R'
        if '1099-b' in name_lower or '1099b' in name_lower:
            return '1099-B'
        if '1099-nec' in name_lower or '1099nec' in name_lower:
            return '1099-NEC'
        if '1099-misc' in name_lower or '1099misc' in name_lower:
            return '1099-MISC'
        return '1099'

    @staticmethod
    def _refine_1098_from_filename(filename: str, default: str) -> str:
        """Detect 1098-T from filename within the 1098 folder."""
        name_lower = filename.lower().replace(' ', '').replace('_', '')
        if '1098-t' in name_lower or '1098t' in name_lower:
            return '1098-T'
        return default

    @staticmethod
    def _categorize_by_filename(filename: str) -> Optional[str]:
        """Categorize a file based solely on filename keywords."""
        name_lower = filename.lower().replace(' ', '').replace('_', '')
        for category, keywords in FORM_KEYWORDS.items():
            for keyword in keywords:
                if keyword.replace('-', '') in name_lower:
                    return category
        return None

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

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
                category=self._categorize_file(file_path),
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
        print("\n" + "=" * 60)
        print("  TAX DOCUMENT INVENTORY")
        print("=" * 60)

        total = 0
        for category, files in sorted(categorized.items()):
            tag = "[structured]" if category in EXTRACTABLE_CATEGORIES else "[OCR]"
            print(f"\n  {category} {tag}:")
            for f in files:
                size_kb = f.size_bytes / 1024
                # Use ASCII-safe filename for print (Windows cp1252 can't handle some Unicode)
                safe_name = f.filename.encode('ascii', errors='replace').decode('ascii')
                print(f"    - {safe_name} ({size_kb:.1f} KB)")
                total += 1

        print(f"\n  Total documents: {total}")
        print("=" * 60)
