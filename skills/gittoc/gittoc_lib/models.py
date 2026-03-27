from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .common import (DEFAULT_PRIORITY, STATE_SET, issue_number,
                     validate_issue_id, validate_priority)


@dataclass(frozen=True)
class Issue:
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
        return {
            "body": self.body,
            "created_at": self.created_at,
            "deps": list(self.deps),
            "id": self.issue_id,
            "labels": list(self.labels),
            "owner": self.owner,
            "priority": self.priority,
            "title": self.title,
            "updated_at": self.updated_at,
        }

    def to_display(self, path: Path, notes_count: int) -> dict:
        data = self.to_record()
        data["notes_count"] = notes_count
        data["path"] = str(path)
        data["state"] = self.state
        return data
