"""Issue data model for gittoc."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .common import (DEFAULT_PRIORITY, STATE_SET, issue_number,
                     validate_issue_id, validate_priority)


@dataclass(frozen=True)
class Issue:
    """Immutable representation of a single gittoc ticket."""

    issue_id: str
    title: str
    body: str
    deps: tuple[str, ...]
    labels: tuple[str, ...]
    owner: str
    priority: int
    created_at: str
    updated_at: str
    state: str

    @classmethod
    def from_path(cls, path: Path) -> "Issue":
        """Load an Issue from its JSON file, deriving state from the parent directory."""
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        state = raw.get(
            "status", path.parent.name if path.parent.name in STATE_SET else "open"
        )
        priority = int(raw.get("priority", DEFAULT_PRIORITY))
        validate_priority(priority)
        return cls(
            issue_id=validate_issue_id(raw["id"]),
            title=raw["title"],
            body=raw.get("body", ""),
            deps=tuple(sorted(set(raw.get("deps", [])), key=issue_number)),
            labels=tuple(raw.get("labels", [])),
            owner=raw.get("owner", ""),
            priority=priority,
            created_at=raw["created_at"],
            updated_at=raw.get("updated_at", raw["created_at"]),
            state=state,
        )

    def to_record(self) -> dict:
        """Serialize the issue to a dict suitable for writing as JSON.

        Empty optional fields (body, deps, labels, owner) are omitted
        to keep ticket files concise and readable.
        """
        record: dict = {
            "created_at": self.created_at,
            "id": self.issue_id,
            "priority": self.priority,
            "title": self.title,
            "updated_at": self.updated_at,
        }
        if self.body:
            record["body"] = self.body
        if self.deps:
            record["deps"] = list(self.deps)
        if self.labels:
            record["labels"] = list(self.labels)
        if self.owner:
            record["owner"] = self.owner
        return record

    def to_display(self, path: Path, notes_count: int) -> dict:
        """Return a display dict augmented with path, state, and note count."""
        data = self.to_record()
        data["notes_count"] = notes_count
        data["path"] = str(path)
        data["state"] = self.state
        return data
