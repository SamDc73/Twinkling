import os
import random
import re

from markdown import Markdown

from utils import get_logger


class NoteManager:
    def __init__(self, notes_directory: str) -> None:
        self.notes_directory = notes_directory
        self.md = Markdown()
        self.logger = get_logger(__name__)

    def is_tech_related(self, content: str) -> bool:
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

    def get_random_tech_note(self) -> tuple[str, str] | tuple[None, None]:
        md_files = [f for f in os.listdir(self.notes_directory) if f.endswith(".md")]
        random.shuffle(md_files)

        for file in md_files:
            try:
                with open(os.path.join(self.notes_directory, file), encoding="utf-8") as f:
                    content = f.read()
                if self.is_tech_related(content):
                    self.logger.info(f"Found tech-related note: {file}")
                    return self.md.convert(content), file
            except Exception as e:
                self.logger.exception(f"Error reading file {file}: {e!s}")

        self.logger.warning("No tech-related notes found")
        return None, None

    def get_tagged_note(self, tag: str) -> tuple[str, str] | tuple[None, None]:
        md_files = [f for f in os.listdir(self.notes_directory) if f.endswith(".md")]
        random.shuffle(md_files)

        for file in md_files:
            with open(os.path.join(self.notes_directory, file), encoding="utf-8") as f:
                content = f.read()
            if f"#{tag}" in content.lower():
                return self.md.convert(content), file

        return None, None

    def get_tech_note_title(self, content: str) -> str:
        title = content.split("\n")[0]
        return re.sub(r"[#*_]", "", title).strip()
