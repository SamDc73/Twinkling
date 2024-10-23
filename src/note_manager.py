from pathlib import Path
from random import shuffle

from markdown import Markdown

from utils import get_logger


class NoteManager:
    """Manager for handling note files and their content."""

    def __init__(self, notes_directory: str) -> None:
        """Initialize the NoteManager.

        Parameters
        ----------
        notes_directory : str
            Path to the directory containing notes.
        """
        self.notes_directory = Path(notes_directory)
        self.md = Markdown()
        self.logger = get_logger(__name__)

    def is_tech_related(self, content: str) -> bool:
        """Check if content is tech-related.

        Parameters
        ----------
        content : str
            Content to check.

        Returns
        -------
        bool
            True if content contains tech-related keywords.
        """
        tech_keywords = [
            "python",
            "javascript",
            "programming",
            "software",
            "data",
            "algorithm",
            "api",
        ]
        return any(keyword in content.lower() for keyword in tech_keywords)

    def _read_file(self, file_path: Path) -> str | None:
        """Read content from a single file safely.

        Parameters
        ----------
        file_path : Path
            Path to the file to read.

        Returns
        -------
        str | None
            File content if successful, None if reading fails.
        """
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception:
            self.logger.exception("Error reading file %s", file_path.name)
            return None

    def get_random_tech_note(self) -> tuple[str, str] | tuple[None, None]:
        """Get a random tech-related note.

        Returns
        -------
        tuple[str, str] | tuple[None, None]
            Tuple of (note content, filename) if found, (None, None) if not found.
        """
        md_files = list(self.notes_directory.glob("*.md"))
        shuffle(md_files)

        for file_path in md_files:
            content = self._read_file(file_path)
            if content is not None and self.is_tech_related(content):
                self.logger.info("Found tech-related note: %s", file_path.name)
                return self.md.convert(content), file_path.name

        self.logger.warning("No tech-related notes found")
        return None, None

    def get_tagged_note(self, tag: str) -> tuple[str, str] | tuple[None, None]:
        """Get a note with a specific tag.

        Parameters
        ----------
        tag : str
            Tag to search for.

        Returns
        -------
        tuple[str, str] | tuple[None, None]
            Tuple of (note content, filename) if found, (None, None) if not found.
        """
        md_files = list(self.notes_directory.glob("*.md"))
        shuffle(md_files)

        for file_path in md_files:
            content = self._read_file(file_path)
            if content is not None and f"#{tag}" in content.lower():
                return self.md.convert(content), file_path.name

        return None, None

    def get_tech_note_title(self, content: str) -> str:
        """Extract title from note content.

        Parameters
        ----------
        content : str
            Note content.

        Returns
        -------
        str
            Title extracted from content.
        """
        title = content.split("\n")[0]
        return title.strip("#* _")
