"""Shared integrity report models and rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .common import EVENT_SUFFIX, ISSUE_RE


@dataclass(frozen=True)
class IntegrityFinding:
    """Single integrity finding produced by ``gittoc fsck``."""

    severity: str
    message: str
    path: str | None = None
    line: int | None = None
    issue_ids: tuple[str, ...] = ()

    def to_record(self) -> dict[str, object]:
        """Convert the finding to a JSON-serializable dict."""
        record: dict[str, object] = {
            "severity": self.severity,
            "message": self.message,
        }
        if self.path is not None:
            record["path"] = self.path
        if self.line is not None:
            record["line"] = self.line
        if self.issue_ids:
            record["issue_ids"] = list(self.issue_ids)
        return record


@dataclass(frozen=True)
class IntegrityReport:
    """Aggregate result of a tracker integrity scan."""

    findings: tuple[IntegrityFinding, ...]
    checked_paths: tuple[str, ...]
    scanned_issues: int
    scanned_event_logs: int

    @property
    def errors(self) -> tuple[IntegrityFinding, ...]:
        """Return the error-level findings."""
        return tuple(
            finding for finding in self.findings if finding.severity == "error"
        )

    @property
    def warnings(self) -> tuple[IntegrityFinding, ...]:
        """Return the warning-level findings."""
        return tuple(
            finding for finding in self.findings if finding.severity == "warning"
        )

    @property
    def ok(self) -> bool:
        """Return True when the scan found no errors or warnings."""
        return not self.findings

    def to_record(self) -> dict[str, object]:
        """Convert the report to a JSON-serializable dict."""
        return {
            "checked_paths": list(self.checked_paths),
            "errors": [finding.to_record() for finding in self.errors],
            "findings": [finding.to_record() for finding in self.findings],
            "ok": self.ok,
            "scanned_event_logs": self.scanned_event_logs,
            "scanned_issues": self.scanned_issues,
            "warnings": [finding.to_record() for finding in self.warnings],
        }


def issue_id_from_path(path: Path) -> str | None:
    """Return the ticket ID encoded in an issue/event path, or None."""
    name = path.name
    if name.endswith(EVENT_SUFFIX):
        candidate = name[: -len(EVENT_SUFFIX)]
    elif name.endswith(".json"):
        candidate = path.stem
    else:
        return None
    return candidate if ISSUE_RE.match(candidate) else None


def render_integrity_report(report: IntegrityReport) -> str:
    """Render an integrity report in a compact human-readable text form."""
    if report.ok:
        return (
            "fsck ok: "
            f"issues={report.scanned_issues} event_logs={report.scanned_event_logs}"
        )
    lines: list[str] = []
    for finding in report.findings:
        location = finding.path or "tracker"
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(f"{finding.severity}: {location}: {finding.message}")
    parts = []
    if report.errors:
        parts.append(f"{len(report.errors)} error(s)")
    if report.warnings:
        parts.append(f"{len(report.warnings)} warning(s)")
    lines.append(f"fsck failed: {', '.join(parts)}")
    return "\n".join(lines)
