"""CSV file reader and form entry parser."""

import csv
from pathlib import Path
from typing import List, Optional, Iterator
import logging

from models.form_entry import FormEntry
from models.enums import FormType
from utils.url_classifier import URLClassifier

logger = logging.getLogger(__name__)


class CSVReader:
    """
    Reader for the forms CSV file.

    Expected CSV columns:
    - census_id: Unique municipality identifier
    - municipality: Municipality name
    - state: State abbreviation
    - rank: Priority rank (1 = most preferred)
    - url: Form URL
    - description: Description of the form/portal
    """

    REQUIRED_COLUMNS = ['census_id', 'municipality', 'state', 'rank', 'url']

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)

        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

    def read_all(self, classify: bool = True) -> List[FormEntry]:
        """
        Read all entries from CSV file.

        Args:
            classify: Whether to auto-classify form types

        Returns:
            List of FormEntry objects
        """
        entries = list(self.iter_entries(classify=classify))
        logger.info(f"Read {len(entries)} form entries from {self.csv_path}")
        return entries

    def iter_entries(self, classify: bool = True) -> Iterator[FormEntry]:
        """
        Iterate over entries without loading all into memory.

        Yields:
            FormEntry objects
        """
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Validate columns
            if reader.fieldnames:
                missing = set(self.REQUIRED_COLUMNS) - set(reader.fieldnames)
                if missing:
                    raise ValueError(f"CSV missing required columns: {missing}")

            for row in reader:
                # Skip empty rows
                if not row.get('url'):
                    continue

                entry = FormEntry(
                    census_id=row['census_id'],
                    municipality=row['municipality'],
                    state=row['state'],
                    rank=int(row.get('rank', 1)),
                    url=row['url'],
                    description=row.get('description', ''),
                )

                if classify:
                    entry.form_type = URLClassifier.classify(entry.url)

                yield entry

    def get_by_census_id(self, census_id: str) -> List[FormEntry]:
        """Get all form entries for a specific census_id."""
        return [e for e in self.iter_entries() if e.census_id == census_id]

    def get_best_per_municipality(self) -> List[FormEntry]:
        """
        Get the best (rank=1) form for each municipality.

        Returns:
            List of FormEntry objects with rank=1
        """
        return [e for e in self.iter_entries() if e.rank == 1]

    def get_by_form_type(self, form_type: FormType) -> List[FormEntry]:
        """Get all entries of a specific form type."""
        return [e for e in self.iter_entries() if e.form_type == form_type]

    def get_statistics(self) -> dict:
        """Get statistics about the CSV contents."""
        entries = self.read_all()

        stats = {
            'total_entries': len(entries),
            'unique_municipalities': len(set(e.census_id for e in entries)),
            'by_form_type': {},
            'by_state': {},
        }

        for entry in entries:
            # Count by form type
            type_name = entry.form_type.name if entry.form_type else 'UNKNOWN'
            stats['by_form_type'][type_name] = stats['by_form_type'].get(type_name, 0) + 1

            # Count by state
            stats['by_state'][entry.state] = stats['by_state'].get(entry.state, 0) + 1

        return stats
