"""Formatting functions for issue output."""

from __future__ import annotations

import json

from .models import Issue


def marker(issue: Issue, tracker) -> str:
    """Return the one-character state marker for an issue."""
    if issue.state in ("closed", "rejected"):
        return "x"
    if tracker.ready(issue):
        return ">"
    if issue.state == "claimed":
        return "!"
    if issue.state == "blocked":
        return "~"
    return "*"


def render_compact(issue: Issue, _tracker) -> str:
    """Render an issue as a single compact line without state marker."""
    return f"{issue.issue_id} p{issue.priority} {issue.state} {issue.title}"


def render_normal(issue: Issue, tracker) -> str:
    """Render an issue as a single annotated line with marker, deps, owner, labels, and note count."""
    deps = f" deps={len(issue.deps)}" if issue.deps else ""
    owner = f" owner={issue.owner}" if issue.owner else ""
    labels = f" labels={','.join(issue.labels)}" if issue.labels else ""
    notes = tracker.note_count(issue.issue_id)
    notes_text = f" notes={notes}" if notes else ""
    return (
        f"{marker(issue, tracker)} {issue.issue_id} p{issue.priority} "
        f"[{issue.state}] {issue.title}{deps}{owner}{labels}{notes_text}"
    )


def render_verbose(issue: Issue, tracker) -> str:
    """Render an issue as a multi-line block with all fields."""
    deps = ", ".join(issue.deps) if issue.deps else "-"
    labels = ", ".join(issue.labels) if issue.labels else "-"
    owner = issue.owner or "-"
    body = issue.body or "-"
    notes = tracker.note_count(issue.issue_id)
    lines = [
        render_normal(issue, tracker),
        f"  deps: {deps}",
        f"  owner: {owner}",
        f"  labels: {labels}",
        f"  notes: {notes}",
        f"  created: {issue.created_at}",
        f"  updated: {issue.updated_at}",
        f"  body: {body}",
    ]
    return "\n".join(lines)


def render_show_text(data: dict) -> str:
    """Render a show-command data dict as human-readable text."""
    lines: list[str] = []
    lines.append(f"{data.get('id', '?')} p{data.get('priority', '?')} [{data.get('state', '?')}] {data.get('title', '')}")
    if data.get("body"):
        lines.append(f"  body: {data['body']}")
    deps = data.get("deps", [])
    lines.append(f"  deps: {', '.join(deps) if deps else '-'}")
    labels = data.get("labels", [])
    lines.append(f"  labels: {', '.join(labels) if labels else '-'}")
    lines.append(f"  owner: {data.get('owner') or '-'}")
    lines.append(f"  created: {data.get('created_at', '-')}")
    lines.append(f"  updated: {data.get('updated_at', '-')}")
    notes_count = data.get("notes_count", data.get("recent_notes_total", 0))
    lines.append(f"  notes: {notes_count}")
    recent_notes = data.get("recent_notes", [])
    if recent_notes:
        lines.append("")
        for note in recent_notes:
            actor = note.get("actor", "?")
            at = note.get("at", "")
            text = note.get("text", "")
            lines.append(f"  [{at}] {actor}: {text}")
    hint = data.get("recent_notes_hint")
    if hint:
        lines.append(f"  ({hint})")
    history = data.get("history")
    if history:
        lines.append("")
        lines.append("  history:")
        for entry in history:
            kind = entry.get("kind", "?")
            at = entry.get("at", "")
            text = entry.get("text", "")
            lines.append(f"    [{at}] {kind}: {text}")
    return "\n".join(lines)


def print_issues(issues: list[Issue], tracker, fmt: str) -> None:
    """Print a list of issues in the requested format."""
    if fmt == "json":
        payload = []
        for issue in issues:
            path = tracker.issue_path(issue.issue_id, issue.state)
            payload.append(
                issue.to_display(
                    path.relative_to(tracker.checkout),
                    tracker.note_count(issue.issue_id),
                )
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    renderer = {
        "compact": render_compact,
        "normal": render_normal,
        "verbose": render_verbose,
    }[fmt]
    for index, issue in enumerate(issues):
        if index and fmt == "verbose":
            print()
        print(renderer(issue, tracker))
