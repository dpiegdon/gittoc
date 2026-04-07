"""Command handler implementations for gittoc CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .common import (
    STATE_ORDER,
    STATE_SET,
    TRACKER_BRANCH,
    default_owner,
    issue_number,
    parse_state,
    run_git,
    validate_issue_id,
)
from .integrity import IntegrityReport, render_integrity_report
from .render import print_issues, render_show_text
from .tracker import RemotePushPullError, Tracker

SHOW_NOTES_LIMIT = 3


def _auto_pull(tracker) -> None:
    """Pull before a mutation if autopush is enabled."""
    if tracker.autopush_enabled():
        tracker.auto_pull()


def _auto_push(tracker) -> None:
    """Push after a mutation if autopush is enabled."""
    if tracker.autopush_enabled():
        tracker.auto_push()


def parse_labels(values: list[str] | None) -> list[str]:
    """Parse repeatable/comma-separated label arguments into a deduplicated list."""
    if not values:
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for value in values:
        for label in value.split(","):
            label = label.strip()
            if not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)
    return labels


def parse_states(values: list[str] | None) -> tuple[str, ...]:
    """Parse repeatable/comma-separated state arguments into a validated tuple."""
    if not values:
        return ()
    states: list[str] = []
    seen: set[str] = set()
    for value in values:
        for state in value.split(","):
            state = state.strip()
            if not state or state in seen:
                continue
            if state not in STATE_SET:
                raise SystemExit(
                    f"invalid state: {state} (valid: {', '.join(STATE_ORDER)})"
                )
            seen.add(state)
            states.append(state)
    return tuple(states)


def parse_issue_ids(values: list[str] | None) -> list[str]:
    """Parse repeatable/comma-separated issue ID arguments into a validated list."""
    if not values:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        for issue_id in value.split(","):
            issue_id = issue_id.strip()
            if not issue_id or issue_id in seen:
                continue
            validate_issue_id(issue_id)
            seen.add(issue_id)
            ids.append(issue_id)
    return ids


def format_history_entry(entry: dict) -> str:
    """Format a single event log entry as a human-readable one-liner."""
    note_id = entry.get("note_id")
    kind = f"note#{note_id}" if note_id else entry["kind"]
    return f"{entry['at']} {kind} {entry['actor']}: {entry['text']}"


def resume_payload(
    tracker: Tracker,
    issue,
    path: Path,
    *,
    notes_limit: int,
    events_limit: int,
    reason: str | None = None,
) -> dict:
    """Build the full resume data dict including recent notes and events."""
    note_count = tracker.note_count(issue.issue_id)
    data = issue.to_display(path.relative_to(tracker.checkout), note_count)
    data["ready"] = tracker.ready(issue)
    if reason:
        data["selection"] = reason
    notes = tracker.filtered_events(issue.issue_id, kinds={"note"}, limit=notes_limit)
    data["recent_notes"] = notes
    data["recent_notes_shown"] = len(notes)
    data["recent_notes_total"] = note_count
    data["recent_events"] = tracker.filtered_events(
        issue.issue_id,
        kinds={"created", "updated", "claimed", "closed", "dependency"},
        limit=events_limit,
    )
    return data


def print_resume_text(data: dict) -> None:
    """Print the resume payload in human-readable text format."""
    marker = ">" if data["ready"] else "*"
    owner = f" owner={data['owner']}" if data.get("owner") else ""
    deps_list = data.get("deps", [])
    deps = f" deps={len(deps_list)}" if deps_list else ""
    selection = f" selection={data['selection']}" if data.get("selection") else ""
    print(
        f"{marker} {data['id']} p{data['priority']} [{data['state']}] {data['title']}{deps}{owner}{selection}"
    )
    if data.get("body"):
        print()
        print(data["body"])
    notes = data["recent_notes"]
    if notes:
        print()
        print("Recent notes:")
        for entry in notes:
            print(f"- {format_history_entry(entry)}")
        if data["recent_notes_total"] > data["recent_notes_shown"]:
            print(
                f"- showing {data['recent_notes_shown']} of {data['recent_notes_total']} notes; "
                f"use `show {data['id']} -n` for all"
            )
    events = data["recent_events"]
    if events:
        print()
        print("Recent events:")
        for entry in events:
            print(f"- {format_history_entry(entry)}")


def cmd_init(_args: argparse.Namespace) -> int:
    """Initialize the tracker worktree and auto-configure the remote if possible."""
    tracker = Tracker.open()
    if not tracker.configured_remote():
        inferred = tracker.effective_remote()
        if inferred:
            tracker.configure_remote(inferred)
    print(f"initialized tracker branch {TRACKER_BRANCH} at {tracker.checkout}")
    return 0


def cmd_remote(args: argparse.Namespace) -> int:
    """Show or configure the remote wiring for the tracker branch."""
    tracker = Tracker.open()
    if args.set:
        status = tracker.configure_remote(args.set)
    elif args.auto:
        remote = tracker.effective_remote()
        if not remote:
            raise SystemExit("no remote could be inferred")
        status = tracker.configure_remote(remote)
    else:
        status = tracker.remote_status()
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        remotes = ", ".join(status["remotes"]) if status["remotes"] else "-"
        print(
            f"remotes={remotes} inferred={status['inferred_remote'] or '-'} "
            f"configured={status['configured_remote'] or '-'} "
            f"effective={status['effective_remote'] or '-'} "
            f"branch_remote={status['branch_config_remote'] or '-'} "
            f"branch_merge={status['branch_config_merge'] or '-'} "
            f"remote_branch_exists={'yes' if status['remote_branch_exists'] else 'no'}"
        )
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    """Fetch and merge the tracker branch from a remote."""
    tracker = Tracker.open()
    remote = args.remote or tracker.effective_remote()
    if not remote:
        print(
            "error: no remote specified and none configured (run: gittoc remote --set <name>)",
            file=sys.stderr,
        )
        return 1
    try:
        status = tracker.pull_remote(remote)
    except RemotePushPullError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = status.get("fsck")
    payload = dict(status)
    if isinstance(report, IntegrityReport):
        payload["fsck"] = report.to_record()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"pulled {TRACKER_BRANCH} from {status['remote']} to {status['head']}")
        if isinstance(report, IntegrityReport) and not report.ok:
            # Findings go to stderr so the pull status line stays parseable on
            # stdout; cmd_fsck uses stdout because the report IS the output.
            print(render_integrity_report(report), file=sys.stderr)
    if isinstance(report, IntegrityReport) and not report.ok:
        return 1
    return 0


def cmd_fsck(args: argparse.Namespace) -> int:
    """Run a read-only integrity scan over tracker issues and event logs."""
    tracker = Tracker.open()
    report = tracker.fsck()
    if args.format == "json":
        print(json.dumps(report.to_record(), indent=2, sort_keys=True))
    else:
        print(render_integrity_report(report))
    return 0 if report.ok else 1


def cmd_push(args: argparse.Namespace) -> int:
    """Push the tracker branch to a remote."""
    tracker = Tracker.open()
    remote = args.remote or tracker.effective_remote()
    if not remote:
        print(
            "error: no remote specified and none configured (run: gittoc remote --set <name>)",
            file=sys.stderr,
        )
        return 1
    try:
        status = tracker.push_remote(remote)
    except RemotePushPullError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"pushed {TRACKER_BRANCH} to {status['remote']} at {status['head']}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new issue and optionally add dependencies."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    issue = tracker.create_issue(
        args.title, args.body or "", parse_labels(args.label), args.priority
    )
    deps = parse_issue_ids(args.dep)
    if deps:
        tracker.set_dependencies(issue.issue_id, deps)
    print(issue.issue_id)
    _auto_push(tracker)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List issues filtered by state, label, and/or readiness."""
    tracker = Tracker.open()
    if args.all:
        states = STATE_ORDER
    else:
        states = parse_states(args.state) or ("open",)
    issues = tracker.list_issues(states)
    if args.label:
        required = set(parse_labels(args.label))
        issues = [issue for issue in issues if required.issubset(issue.labels)]
    if args.sort == "id":
        issues.sort(key=lambda i: issue_number(i.issue_id))
    print_issues(issues, tracker, args.format)
    return 0


def cmd_claimed(args: argparse.Namespace) -> int:
    """List all currently claimed issues."""
    tracker = Tracker.open()
    issues = tracker.list_issues(("claimed",))
    print_issues(issues, tracker, args.format)
    return 0


def cmd_unblocked(args: argparse.Namespace) -> int:
    """List all open issues that have no unresolved blocking dependencies."""
    tracker = Tracker.open()
    issues = tracker.ready_issues()
    print_issues(issues, tracker, args.format)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    """Claim one or more issues, assigning them to the given or inferred owner."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    owner = args.owner or default_owner()
    issue_ids = parse_issue_ids(args.issue_ids)
    issues = []
    for issue_id in issue_ids:
        issues.append(
            tracker.update_issue(
                issue_id,
                state="claimed",
                owner=owner,
                message=f"Claim issue {issue_id} for {owner}",
                event_kind="claimed",
                event_text=owner,
                event_actor=owner,
            )
        )
    print_issues(issues, tracker, args.format)
    _auto_push(tracker)
    return 0


def cmd_labels(args: argparse.Namespace) -> int:
    """List all labels in use, with counts, across open (or all) tickets."""
    tracker = Tracker.open()
    states = STATE_ORDER if args.all else ("open",)
    counts: dict[str, int] = {}
    for issue in tracker.list_issues(states):
        for label in issue.labels:
            counts[label] = counts.get(label, 0) + 1
    if args.format == "json":
        print(json.dumps(counts, indent=2, sort_keys=True))
    else:
        for label in sorted(counts):
            print(f"{label:<20} {counts[label]}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    """Reject an issue (mark as won't-do / abandoned) and print confirmation."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    actor = args.actor or default_owner()
    issue = tracker.reject_issue(args.issue_id, actor=actor)
    print_issues([issue], tracker, args.format)
    _auto_push(tracker)
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Print a one-line summary of issue counts by state."""
    tracker = Tracker.open()
    counts = tracker.summary()
    if args.format == "json":
        print(json.dumps(counts, indent=2, sort_keys=True))
    else:
        parts = [
            f"open={counts['open']}",
            f"claimed={counts['claimed']}",
            f"blocked={counts['blocked']}",
            f"closed={counts['closed']}",
            f"rejected={counts['rejected']}",
            f"ready={counts['ready']}",
        ]
        print(" ".join(parts))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Print a single issue with optional notes/history detail."""
    tracker = Tracker.open()
    issue, path = tracker.load_issue(args.issue_id)
    note_count = tracker.note_count(issue.issue_id)
    data = issue.to_display(path.relative_to(tracker.checkout), note_count)
    limit = args.limit
    if args.all:
        # -a: everything — full event history; notes are part of history, shown once
        data["history"] = tracker.filtered_events(issue.issue_id, limit=limit)
    elif args.notes:
        # -n: all notes, no limit (unless -l is set)
        notes = tracker.filtered_events(issue.issue_id, kinds={"note"}, limit=limit)
        data["recent_notes"] = notes
        data["recent_notes_shown"] = len(notes)
        data["recent_notes_total"] = note_count
    else:
        # Default: 3 recent notes (or -l N)
        notes_limit = limit if limit is not None else SHOW_NOTES_LIMIT
        recent_notes = tracker.filtered_events(
            issue.issue_id, kinds={"note"}, limit=notes_limit
        )
        data["recent_notes"] = recent_notes
        data["recent_notes_shown"] = len(recent_notes)
        data["recent_notes_total"] = note_count
        if note_count > len(recent_notes):
            data["recent_notes_hint"] = (
                f"showing {len(recent_notes)} of {note_count} notes; "
                f"use `show {args.issue_id} -n` for all"
            )
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(render_show_text(data))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update one or more fields of an existing issue."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    state = parse_state(args.state)
    add_labels = parse_labels(args.label)
    replace_labels = parse_labels(args.replace_label)
    remove_labels = set(parse_labels(args.remove_label))
    if replace_labels and (add_labels or remove_labels):
        raise SystemExit(
            "cannot combine --replace-label with --label or --remove-label"
        )
    labels = None
    if replace_labels:
        labels = replace_labels
    elif add_labels or remove_labels:
        issue, _ = tracker.load_issue(args.issue_id)
        labels = list(issue.labels)
        for label in add_labels:
            if label not in labels:
                labels.append(label)
        if remove_labels:
            labels = [label for label in labels if label not in remove_labels]
    has_changes = any(
        [
            args.title is not None,
            args.body is not None,
            state is not None,
            args.owner is not None,
            labels is not None,
            args.priority is not None,
        ]
    )
    if not has_changes:
        print("no fields to update", file=sys.stderr)
        return 1
    issue = tracker.update_issue(
        args.issue_id,
        title=args.title,
        body=args.body,
        state=state,
        owner=args.owner,
        labels=labels,
        priority=args.priority,
        event_text="fields updated",
    )
    print(issue.issue_id)
    _auto_push(tracker)
    return 0


def cmd_dep(args: argparse.Namespace) -> int:
    """Add or remove blocking dependencies for an issue."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    dep_ids = parse_issue_ids(args.dep_ids)
    if args.remove:
        issue = tracker.remove_dependencies(args.issue_id, dep_ids)
    else:
        issue = tracker.set_dependencies(args.issue_id, dep_ids)
    print(issue.issue_id)
    _auto_push(tracker)
    return 0


def cmd_grep(args: argparse.Namespace) -> int:
    """Search ticket files for a pattern using grep."""
    grep_args = [a for a in (args.grep_args or []) if a != "--"]
    if not grep_args:
        print("error: grep requires a pattern", file=sys.stderr)
        return 1
    pattern = grep_args[0]
    extra_flags = grep_args[1:]
    tracker = Tracker.open()
    if args.all:
        states = STATE_ORDER
    else:
        states = parse_states(args.state) or ("open",)
    files: list[str] = []
    for state in states:
        state_path = tracker.state_dir(state)
        if state_path.is_dir():
            files.extend(
                str(p.relative_to(tracker.checkout))
                for p in sorted(state_path.iterdir())
                if p.is_file()
            )
    if not files:
        return 1
    cmd = ["grep", "-H"] + extra_flags + ["--", pattern] + files
    result = subprocess.run(cmd, cwd=tracker.checkout)
    return result.returncode


def cmd_close(args: argparse.Namespace) -> int:
    """Mark an issue as closed (done) and print confirmation."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    actor = args.actor or default_owner()
    issue = tracker.update_issue(
        args.issue_id,
        state="closed",
        message=f"Close issue {args.issue_id}",
        event_kind="closed",
        event_actor=actor,
    )
    print_issues([issue], tracker, args.format)
    _auto_push(tracker)
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Print git log for a specific issue file, or the full tracker branch."""
    tracker = Tracker.open()
    reverse = ["--reverse"] if args.reverse else []
    if args.issue_id:
        _, path = tracker.load_issue(args.issue_id)
        rel = path.relative_to(tracker.checkout)
        git_args = ["log", *reverse, "--follow", "--oneline", "--", str(rel)]
    else:
        git_args = ["log", *reverse, "--oneline"]
    out = run_git(git_args, cwd=tracker.checkout)
    print(out.stdout.strip())
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """Append a note to an issue and print its ID."""
    tracker = Tracker.open()
    _auto_pull(tracker)
    issue = tracker.add_note(args.issue_id, args.text, actor=args.actor)
    print(issue.issue_id)
    _auto_push(tracker)
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Show recovery context for a specific or auto-selected issue."""
    tracker = Tracker.open()
    reason: str | None = None
    if args.issue_id:
        issue, path = tracker.load_issue(args.issue_id)
    else:
        owner = args.owner or default_owner()
        issue, reason = tracker.resume_issue(owner)
        if issue is None:
            if args.format == "json":
                print("null")
            else:
                print("no resumable issues")
            return 0
        _, path = tracker.load_issue(issue.issue_id)
    data = resume_payload(
        tracker,
        issue,
        path,
        notes_limit=args.notes_limit,
        events_limit=args.events_limit,
        reason=reason,
    )
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print_resume_text(data)
    return 0
