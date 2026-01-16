"""Form entry data model representing a row from the CSV file."""

from dataclasses import dataclass
from typing import Optional

from .enums import FormType


@dataclass
class FormEntry:
    """Represents a single form entry from the CSV file."""
    census_id: str
    municipality: str
    state: str
    rank: int
    url: str
    description: str
    form_type: Optional[FormType] = None

    @property
    def unique_id(self) -> str:
        """Unique identifier for this form entry."""
        return f"{self.census_id}_{self.rank}"

    @property
    def display_name(self) -> str:
        """Human-readable name for logging."""
        return f"{self.municipality}, {self.state} (Rank {self.rank})"
