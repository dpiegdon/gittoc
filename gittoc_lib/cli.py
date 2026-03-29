"""Command-line interface: argument parsing and command implementations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    DEFAULT_PRIORITY,
    STATE_ORDER,
    TRACKER_BRANCH,
    default_owner,
    issue_number,
    parse_state,
    run_git,
)
from .render import print_issues
from .tracker import StaleTrackerError, Tracker

SHOW_NOTES_LIMIT = 3
COMMAND_ALIASES = {
    "l": "list",
    "s": "summary",
    "r": "resume",
    "c": "claim",
    "n": "note",
    "sh": "show",
    "pl": "pull",
    "pul": "pull",
    "ps": "push",
    "pus": "push",
}


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


def select_fields(data: dict, fields: list[str] | None) -> dict:
    """Return a subset of data containing only the requested fields, or all if none given."""
    if not fields:
        return data
    selected: dict = {}
    for field in fields:
        if field in data:
            selected[field] = data[field]
    return selected


def format_history_entry(entry: dict) -> str:
    """Format a single event log entry as a human-readable one-liner."""
    return f"{entry['at']} {entry['kind']} {entry['actor']}: {entry['text']}"


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
    data = issue.to_display(
        path.relative_to(tracker.checkout), tracker.note_count(issue.issue_id)
    )
    data["ready"] = tracker.ready(issue)
    if reason:
        data["selection"] = reason
    notes = tracker.filtered_events(issue.issue_id, kinds={"note"}, limit=notes_limit)
    note_count = tracker.note_count(issue.issue_id)
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
                f"use `history {data['id']} --notes-only` for more"
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
    _print_init_checklist(tracker.repo)
    return 0


def _print_init_checklist(repo: Path) -> None:
    """Print a post-install checklist of optional setup steps."""
    skill_link = repo / ".claude" / "skills" / "gittoc.md"
    alias_proc = run_git(["config", "alias.toc"], cwd=repo, check=False)
    has_alias = alias_proc.returncode == 0

    lines = []
    if not skill_link.exists():
        lines.append(
            "  [ ] Claude Code skill symlink missing — run:\n"
            "        mkdir -p .claude/skills && ln -s ../../tools/gittoc/SKILL.md .claude/skills/gittoc.md"
        )
    else:
        lines.append(f"  [x] Claude Code skill symlink: {skill_link.relative_to(repo)}")

    if not has_alias:
        lines.append(
            "  [ ] git alias not set — run:\n"
            "        printf '[alias]\\n    toc = !tools/gittoc/gittoc\\n' >> .git/config"
        )
    else:
        lines.append(f"  [x] git alias: git toc = {alias_proc.stdout.strip()}")

    if lines:
        print("\nSetup checklist:")
        print("\n".join(lines))


def cmd_refresh(args: argparse.Namespace) -> int:
    """Reload the stale-check baseline and print the current HEAD and issue counts."""
    tracker = Tracker.open()
    head = tracker.refresh()
    counts = tracker.summary()
    if args.format == "json":
        print(
            json.dumps(
                {"head": head, "summary": counts},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"head={head} open={counts['open']} claimed={counts['claimed']} "
            f"blocked={counts['blocked']} closed={counts['closed']} ready={counts['ready']}"
        )
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
            "error: no remote specified and none configured (run: gittoc remote --set <name>)"
        )
        return 1
    status = tracker.pull_remote(remote)
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"pulled {TRACKER_BRANCH} from {status['remote']} to {status['head']}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    """Push the tracker branch to a remote."""
    tracker = Tracker.open()
    remote = args.remote or tracker.effective_remote()
    if not remote:
        print(
            "error: no remote specified and none configured (run: gittoc remote --set <name>)"
        )
        return 1
    status = tracker.push_remote(remote)
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"pushed {TRACKER_BRANCH} to {status['remote']} at {status['head']}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new issue and print its ID."""
    tracker = Tracker.open()
    issue = tracker.create_issue(
        args.title, args.body or "", args.label or [], args.priority
    )
    print(issue.issue_id)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List issues filtered by state, label, and/or readiness."""
    tracker = Tracker.open()
    if args.all:
        states = STATE_ORDER
    elif args.state:
        states = tuple(args.state)
    else:
        states = ("open",)
    issues = tracker.list_issues(states)
    if args.ready_only:
        issues = [issue for issue in issues if tracker.ready(issue)]
    if args.label:
        required = set(args.label)
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


def cmd_ready(args: argparse.Namespace) -> int:
    """List all open issues that have no unresolved blocking dependencies."""
    tracker = Tracker.open()
    issues = tracker.ready_issues()
    print_issues(issues, tracker, args.format)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    """Claim one or more issues, assigning them to the given or inferred owner."""
    tracker = Tracker.open()
    owner = args.owner or default_owner()
    issues = []
    for issue_id in args.issue_ids:
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
    """Reject an issue (mark as won't-do / abandoned) and print its ID."""
    tracker = Tracker.open()
    issue = tracker.reject_issue(args.issue_id)
    print(issue.issue_id)
    return 0


def cmd_summary(_args: argparse.Namespace) -> int:
    """Print a one-line summary of issue counts by state."""
    tracker = Tracker.open()
    counts = tracker.summary()
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
    """Print a single issue as a JSON object with optional history and field filtering."""
    tracker = Tracker.open()
    issue, path = tracker.load_issue(args.issue_id)
    data = issue.to_display(
        path.relative_to(tracker.checkout), tracker.note_count(issue.issue_id)
    )
    recent_notes = tracker.filtered_events(
        issue.issue_id, kinds={"note"}, limit=SHOW_NOTES_LIMIT
    )
    recent_notes_total = tracker.note_count(issue.issue_id)
    data["recent_notes"] = recent_notes
    data["recent_notes_shown"] = len(recent_notes)
    data["recent_notes_total"] = recent_notes_total
    if recent_notes_total > len(recent_notes):
        data["recent_notes_hint"] = (
            f"showing {len(recent_notes)} of {recent_notes_total} notes; "
            f"use `history {args.issue_id} --notes-only` for more"
        )
    if args.history:
        data["history"] = tracker.event_entries(issue.issue_id)
    data = select_fields(data, args.field)
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update one or more fields of an existing issue."""
    tracker = Tracker.open()
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
    return 0


def cmd_dep(args: argparse.Namespace) -> int:
    """Add one or more blocking dependencies to an issue."""
    tracker = Tracker.open()
    issue = tracker.set_dependencies(args.issue_id, args.dep_ids)
    print(issue.issue_id)
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    """Mark an issue as closed (done) and print its ID."""
    tracker = Tracker.open()
    issue = tracker.update_issue(
        args.issue_id,
        state="closed",
        message=f"Close issue {args.issue_id}",
        event_kind="closed",
    )
    print(issue.issue_id)
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Print git log for a specific issue file, or the full tracker branch."""
    tracker = Tracker.open()
    if args.issue_id:
        _, path = tracker.load_issue(args.issue_id)
        rel = path.relative_to(tracker.checkout)
        git_args = ["log", "--reverse", "--follow", "--oneline", "--", str(rel)]
    else:
        git_args = ["log", "--reverse", "--oneline"]
    out = run_git(git_args, cwd=tracker.checkout)
    print(out.stdout.strip())
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """Append a note to an issue and print its ID."""
    tracker = Tracker.open()
    issue = tracker.add_note(args.issue_id, args.text, actor=args.actor)
    print(issue.issue_id)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Print the event history for an issue, optionally filtered by kind."""
    tracker = Tracker.open()
    kinds = set(args.kind or [])
    if args.notes_only:
        kinds.add("note")
    entries = tracker.filtered_events(
        args.issue_id, kinds=kinds or None, limit=args.limit
    )
    if args.format == "json":
        print(json.dumps(entries, indent=2, sort_keys=True))
        return 0
    for entry in entries:
        print(format_history_entry(entry))
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


def add_format_argument(
    parser: argparse.ArgumentParser, default: str = "normal"
) -> None:
    """Add -f/--format with compact/normal/verbose/json choices to a subcommand parser."""
    parser.add_argument(
        "-f",
        "--format",
        choices=("compact", "normal", "verbose", "json"),
        default=default,
        help="output format (default: %(default)s)",
    )


def add_text_format_argument(parser: argparse.ArgumentParser) -> None:
    """Add -f/--format with text/json choices to a subcommand parser."""
    parser.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser with all subcommands registered."""
    parser = argparse.ArgumentParser(prog="gittoc")
    sub = parser.add_subparsers(dest="command", required=True)

    claim_parser = sub.add_parser("claim", help="claim one or more issues")
    claim_parser.add_argument(
        "issue_ids",
        nargs="+",
        metavar="issue_id",
        help="ticket(s) to claim, e.g. T-42 T-43",
    )
    claim_parser.add_argument(
        "--owner",
        help="owner name (default: $GITTOC_OWNER or $USER)",
    )
    add_format_argument(claim_parser)
    claim_parser.set_defaults(func=cmd_claim)

    claimed_parser = sub.add_parser("claimed", help="list all currently claimed issues")
    add_format_argument(claimed_parser)
    claimed_parser.set_defaults(func=cmd_claimed)

    close_parser = sub.add_parser("close", help="mark an issue as done")
    close_parser.add_argument("issue_id", help="ticket to close, e.g. T-42")
    close_parser.set_defaults(func=cmd_close)

    dep_parser = sub.add_parser(
        "dep",
        help="add blocking dependencies to an issue",
        description="dep ISSUE_ID DEP_ID [DEP_ID ...] — ISSUE_ID depends on all listed DEP_IDs (DEP_IDs must complete first)",
    )
    dep_parser.add_argument(
        "issue_id", help="ticket that depends on the others, e.g. T-4"
    )
    dep_parser.add_argument(
        "dep_ids",
        nargs="+",
        metavar="dep_id",
        help="one or more tickets that must complete before ISSUE_ID, e.g. T-1 T-2 T-3",
    )
    dep_parser.set_defaults(func=cmd_dep)

    history_parser = sub.add_parser("history", help="show per-issue event history")
    history_parser.add_argument("issue_id", help="ticket to inspect, e.g. T-42")
    history_parser.add_argument(
        "--limit",
        type=int,
        help="maximum number of entries to show",
    )
    history_parser.add_argument(
        "--kind",
        action="append",
        help="filter by event kind (repeatable)",
    )
    history_parser.add_argument(
        "--notes-only",
        action="store_true",
        help="show only note events",
    )
    add_text_format_argument(history_parser)
    history_parser.set_defaults(func=cmd_history)

    init_parser = sub.add_parser("init", help="initialize tracker worktree")
    init_parser.set_defaults(func=cmd_init)

    labels_parser = sub.add_parser(
        "labels", help="list all labels in use across tickets with counts"
    )
    labels_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="include closed tickets (default: open only)",
    )
    add_text_format_argument(labels_parser)
    labels_parser.set_defaults(func=cmd_labels)

    list_parser = sub.add_parser("list", help="list issues ordered by priority")
    list_parser.add_argument(
        "-s",
        "--state",
        action="append",
        choices=STATE_ORDER,
        help="include this state (repeatable; default: open)",
    )
    list_parser.add_argument(
        "-l",
        "--label",
        action="append",
        metavar="LABEL",
        help="filter to tickets carrying this label (repeatable, AND)",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="show all states",
    )
    list_parser.add_argument(
        "--ready-only",
        action="store_true",
        help="show only tickets with no blocking dependencies",
    )
    list_parser.add_argument(
        "--sort",
        choices=["priority", "id"],
        default="priority",
        help="sort order: priority (default) or id (chronological)",
    )
    add_format_argument(list_parser)
    list_parser.set_defaults(func=cmd_list)

    log_parser = sub.add_parser(
        "log", help="show git history for an issue, or all recent tracker changes"
    )
    log_parser.add_argument(
        "issue_id",
        nargs="?",
        help="ticket to inspect; omit to show full tracker branch log",
    )
    log_parser.set_defaults(func=cmd_log)

    new_parser = sub.add_parser("new", help="create an issue")
    new_parser.add_argument("title", help="one-line summary of the issue")
    new_parser.add_argument("-b", "--body", help="longer description or context")
    new_parser.add_argument(
        "-l",
        "--label",
        action="append",
        metavar="LABEL",
        help="tag for this issue (repeatable)",
    )
    new_parser.add_argument(
        "-p",
        "--priority",
        type=int,
        default=DEFAULT_PRIORITY,
        help=f"1 (highest) to 5 (lowest), default {DEFAULT_PRIORITY}",
    )
    new_parser.set_defaults(func=cmd_new)

    note_parser = sub.add_parser("note", help="append a note to an issue")
    note_parser.add_argument("issue_id", help="ticket to annotate, e.g. T-42")
    note_parser.add_argument("text", help="note text")
    note_parser.add_argument(
        "--actor",
        help="override actor name (default: $GITTOC_OWNER or $USER)",
    )
    note_parser.set_defaults(func=cmd_note)

    pull_parser = sub.add_parser(
        "pull", help="fetch and merge the tracker branch from a remote"
    )
    pull_parser.add_argument(
        "remote", nargs="?", help="remote name (default: configured gittoc remote)"
    )
    add_text_format_argument(pull_parser)
    pull_parser.set_defaults(func=cmd_pull)

    push_parser = sub.add_parser("push", help="push the tracker branch to a remote")
    push_parser.add_argument(
        "remote", nargs="?", help="remote name (default: configured gittoc remote)"
    )
    add_text_format_argument(push_parser)
    push_parser.set_defaults(func=cmd_push)

    ready_parser = sub.add_parser("ready", help="list ready open issues by priority")
    add_format_argument(ready_parser)
    ready_parser.set_defaults(func=cmd_ready)

    reject_parser = sub.add_parser(
        "reject", help="mark an issue as won't-do / abandoned"
    )
    reject_parser.add_argument("issue_id", help="ticket to reject, e.g. T-42")
    reject_parser.set_defaults(func=cmd_reject)

    refresh_parser = sub.add_parser(
        "refresh", help="reload tracker state after conflicts"
    )
    add_text_format_argument(refresh_parser)
    refresh_parser.set_defaults(func=cmd_refresh)

    remote_parser = sub.add_parser(
        "remote", help="show or configure tracker remote wiring"
    )
    remote_parser.add_argument(
        "--set",
        metavar="REMOTE",
        help="configure tracker to use this remote",
    )
    remote_parser.add_argument(
        "--auto",
        action="store_true",
        help="infer and configure remote automatically",
    )
    add_text_format_argument(remote_parser)
    remote_parser.set_defaults(func=cmd_remote)

    resume_parser = sub.add_parser(
        "resume", help="show recovery context for a specific or auto-selected issue"
    )
    resume_parser.add_argument(
        "issue_id",
        nargs="?",
        help="ticket to resume; omit to auto-select by priority and ownership",
    )
    resume_parser.add_argument(
        "--owner",
        help="owner for auto-selection (default: $GITTOC_OWNER or $USER)",
    )
    resume_parser.add_argument(
        "--notes-limit",
        type=int,
        default=3,
        help="number of recent notes to include (default: 3)",
    )
    resume_parser.add_argument(
        "--events-limit",
        type=int,
        default=3,
        help="number of recent events to include (default: 3)",
    )
    add_text_format_argument(resume_parser)
    resume_parser.set_defaults(func=cmd_resume)

    show_parser = sub.add_parser("show", help="show one issue as JSON")
    show_parser.add_argument("issue_id", help="ticket to show, e.g. T-42")
    show_parser.add_argument(
        "--history",
        action="store_true",
        help="include full event history",
    )
    show_parser.add_argument(
        "--field",
        action="append",
        metavar="FIELD",
        help="show only this field (repeatable)",
    )
    show_parser.set_defaults(func=cmd_show)

    summary_parser = sub.add_parser("summary", help="print ticket counts by state")
    summary_parser.set_defaults(func=cmd_summary)

    update_parser = sub.add_parser("update", help="update issue fields")
    update_parser.add_argument("issue_id", help="ticket to update, e.g. T-42")
    update_parser.add_argument("-t", "--title", help="new title")
    update_parser.add_argument("-b", "--body", help="new body text")
    update_parser.add_argument("--state", choices=STATE_ORDER, help="new state")
    update_parser.add_argument(
        "--owner",
        help="assign to this owner",
    )
    update_parser.add_argument(
        "-l",
        "--label",
        action="append",
        metavar="LABEL",
        help="add label(s); repeatable and comma-separated",
    )
    update_parser.add_argument(
        "-L",
        "--replace-label",
        action="append",
        metavar="LABEL",
        help="replace all labels with this set; repeatable and comma-separated",
    )
    update_parser.add_argument(
        "-x",
        "--remove-label",
        action="append",
        metavar="LABEL",
        help="remove label(s); repeatable and comma-separated",
    )
    update_parser.add_argument(
        "-p",
        "--priority",
        type=int,
        help="1 (highest) to 5 (lowest)",
    )
    update_parser.set_defaults(func=cmd_update)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse argv, resolve aliases, dispatch to the appropriate command."""
    if argv is None:
        argv = __import__("sys").argv[1:]
    else:
        argv = list(argv)
    if argv:
        argv[0] = COMMAND_ALIASES.get(argv[0], argv[0])
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except StaleTrackerError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2
