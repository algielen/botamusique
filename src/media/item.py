import logging
from typing import Any


class ValidationFailedError(Exception):
    def __init__(self, msg: str | None = None) -> None:
        self.msg = msg


class PreparationFailedError(Exception):
    def __init__(self, msg: str | None = None) -> None:
        self.msg = msg


class BaseItem:
    def __init__(self) -> None:
        self.log = logging.getLogger("bot")
        self.type = "base"
        self.id = ""
        self.title = ""
        self.path = ""
        self.tags: list[str] = []
        self.keywords = ""
        self.duration = 0
        self.version = 0  # if version increase, wrapper will re-save this item
        self.ready = "pending"  # pending - is_valid() -> validated - prepare() -> yes, failed

    def _load_base_from_dict(self, d: dict[str, Any]) -> None:
        self.id = d['id']
        self.ready = d['ready']
        self.tags = d['tags']
        self.title = d['title']
        self.path = d['path']
        self.keywords = d['keywords']
        self.duration = d['duration']

    def is_ready(self) -> bool:
        return True if self.ready == "yes" else False

    def is_failed(self) -> bool:
        return True if self.ready == "failed" else False

    def validate(self) -> None:
        raise ValidationFailedError(None)

    def uri(self) -> str:
        raise NotImplementedError

    def prepare(self) -> bool:
        return True

    def add_tags(self, tags: list[str]) -> None:
        for tag in tags:
            if tag and tag not in self.tags:
                self.tags.append(tag)
                self.version += 1

    def remove_tags(self, tags: list[str]) -> None:
        for tag in tags:
            if tag in self.tags:
                self.tags.remove(tag)
                self.version += 1

    def clear_tags(self) -> None:
        if len(self.tags) > 0:
            self.tags = []
            self.version += 1

    def format_song_string(self, user: str) -> str:
        return self.id

    def format_current_playing(self, user: str) -> str:
        return self.id

    def format_title(self) -> str:
        return self.title

    def format_debug_string(self) -> str:
        return self.id

    def display_type(self) -> str:
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type,
                "id": self.id,
                "ready": self.ready,
                "title": self.title,
                "path": self.path,
                "tags": self.tags,
                "keywords": self.keywords,
                "duration": self.duration}
