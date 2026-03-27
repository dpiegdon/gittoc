from __future__ import annotations

import json

from .models import Issue


def marker(issue: Issue, tracker) -> str:
    if issue.state == "closed":
        return "x"
    if tracker.ready(issue):
        return ">"
    if issue.state == "claimed":
        return "!"
    if issue.state == "blocked":
        return "~"
    return "*"


def render_compact(issue: Issue, tracker) -> str:
    return f"{issue.issue_id} p{issue.priority} {issue.state} {issue.title}"


def render_normal(issue: Issue, tracker) -> str:
    deps = f" deps={len(issue.deps)}" if issue.deps else ""
    owner = f" owner={issue.owner}" if issue.owner else ""
    notes = tracker.note_count(issue.issue_id)
    notes_text = f" notes={notes}" if notes else ""
    return (
        f"{marker(issue, tracker)} {issue.issue_id} p{issue.priority} "
        f"[{issue.state}] {issue.title}{deps}{owner}{notes_text}"
    )


def render_verbose(issue: Issue, tracker) -> str:
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


def print_issues(issues: list[Issue], tracker, fmt: str) -> None:
    if fmt == "json":
        payload = []
        for issue in issues:
            _, path = tracker.load_issue(issue.issue_id)
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
