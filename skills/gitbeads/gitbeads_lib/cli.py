from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import (
    DEFAULT_PRIORITY,
    STATE_ORDER,
    default_owner,
    parse_state,
    TRACKER_BRANCH,
    run_git,
)
from .render import print_issues
from .tracker import Tracker, StaleTrackerError


def select_fields(data: dict, fields: list[str] | None) -> dict:
    if not fields:
        return data
    selected: dict = {}
    for field in fields:
        if field in data:
            selected[field] = data[field]
    return selected


def cmd_init(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    print(f"initialized tracker branch {TRACKER_BRANCH} at {tracker.checkout}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
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


def cmd_new(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issue = tracker.create_issue(args.title, args.body or "", args.label or [], args.priority)
    print(issue.issue_id)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
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
    print_issues(issues, tracker, args.format)
    return 0


def cmd_ready(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    print_issues(tracker.ready_issues(), tracker, args.format)
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issues = tracker.ready_issues()
    if not issues:
        print("no ready issues")
        return 0
    issue = issues[0]
    owner = args.owner or default_owner()
    if args.claim:
        issue = tracker.update_issue(
            issue.issue_id,
            state="claimed",
            owner=owner,
            message=f"Claim issue {issue.issue_id} for {owner}",
            event_kind="claimed",
            event_text=owner,
            event_actor=owner,
        )
    print_issues([issue], tracker, args.format)
    if args.show_body and issue.body and args.format != "json":
        print()
        print(issue.body)
    return 0


def cmd_ready_one(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issues = tracker.ready_issues()
    if not issues:
        if args.format == "json":
            print("null")
        else:
            print("no ready issues")
        return 0
    issue = issues[0]
    _, path = tracker.load_issue(issue.issue_id)
    data = issue.to_display(path.relative_to(tracker.checkout), tracker.note_count(issue.issue_id))
    data = select_fields(data, args.field)
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print_issues([issue], tracker, "normal")
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    owner = args.owner or default_owner()
    issue = tracker.update_issue(
        args.issue_id,
        state="claimed",
        owner=owner,
        message=f"Claim issue {args.issue_id} for {owner}",
        event_kind="claimed",
        event_text=owner,
        event_actor=owner,
    )
    print_issues([issue], tracker, args.format)
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    counts = tracker.summary()
    print(
        " ".join(
            [
                f"open={counts['open']}",
                f"claimed={counts['claimed']}",
                f"blocked={counts['blocked']}",
                f"closed={counts['closed']}",
                f"ready={counts['ready']}",
            ]
        )
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issue, path = tracker.load_issue(args.issue_id)
    data = issue.to_display(path.relative_to(tracker.checkout), tracker.note_count(issue.issue_id))
    if args.history:
        data["history"] = tracker.event_entries(issue.issue_id)
    data = select_fields(data, args.field)
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    state = parse_state(args.state or args.status)
    issue = tracker.update_issue(
        args.issue_id,
        title=args.title,
        body=args.body,
        state=state,
        owner=args.owner,
        labels=args.label,
        priority=args.priority,
        event_text="fields updated",
    )
    print(issue.issue_id)
    return 0


def cmd_dep(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issue = tracker.set_dependencies(args.issue_id, args.dep_ids)
    print(issue.issue_id)
    return 0


def cmd_close(args: argparse.Namespace) -> int:
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
    tracker = Tracker.open()
    _, path = tracker.load_issue(args.issue_id)
    rel = path.relative_to(tracker.checkout)
    out = run_git(["log", "--follow", "--oneline", "--", str(rel)], cwd=tracker.checkout)
    print(out.stdout.strip())
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    issue = tracker.add_note(args.issue_id, args.text, actor=args.actor)
    print(issue.issue_id)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    entries = tracker.event_entries(args.issue_id)
    if args.format == "json":
        print(json.dumps(entries, indent=2, sort_keys=True))
        return 0
    limit = args.limit if args.limit is not None else len(entries)
    for entry in entries[-limit:]:
        print(f"{entry['at']} {entry['kind']} {entry['actor']}: {entry['text']}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    output = Path(args.output).resolve() if args.output else None
    path = tracker.export_issue(args.issue_id, output)
    try:
        rel = path.relative_to(tracker.repo)
        print(rel)
    except ValueError:
        print(path)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    input_path = Path(args.input).resolve() if args.input else None
    issue = tracker.import_issue(args.issue_id, input_path)
    print(issue.issue_id)
    return 0


def add_format_argument(parser: argparse.ArgumentParser, default: str = "normal") -> None:
    parser.add_argument(
        "--format",
        choices=("compact", "normal", "verbose", "json"),
        default=default,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skills/gitbeads/gitbeads")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="initialize tracker worktree and migrate layout")
    init_parser.set_defaults(func=cmd_init)

    refresh_parser = sub.add_parser("refresh", help="reload tracker state after conflicts")
    refresh_parser.add_argument("--format", choices=("text", "json"), default="text")
    refresh_parser.set_defaults(func=cmd_refresh)

    new_parser = sub.add_parser("new", help="create an issue")
    new_parser.add_argument("title")
    new_parser.add_argument("--body")
    new_parser.add_argument("--label", action="append")
    new_parser.add_argument("--priority", type=int, default=DEFAULT_PRIORITY)
    new_parser.set_defaults(func=cmd_new)

    list_parser = sub.add_parser("list", help="list issues ordered by priority")
    list_parser.add_argument("--state", action="append", choices=STATE_ORDER)
    list_parser.add_argument("--all", action="store_true")
    list_parser.add_argument("--ready-only", action="store_true")
    add_format_argument(list_parser)
    list_parser.set_defaults(func=cmd_list)

    ready_parser = sub.add_parser("ready", help="list ready open issues by priority")
    add_format_argument(ready_parser)
    ready_parser.set_defaults(func=cmd_ready)

    ready_one_parser = sub.add_parser(
        "ready-one", help="show the highest-priority ready issue as a single payload"
    )
    ready_one_parser.add_argument("--format", choices=("text", "json"), default="json")
    ready_one_parser.add_argument("--field", action="append")
    ready_one_parser.set_defaults(func=cmd_ready_one)

    next_parser = sub.add_parser("next", help="show or claim the highest-priority ready issue")
    next_parser.add_argument("--claim", action="store_true")
    next_parser.add_argument("--owner")
    next_parser.add_argument("--show-body", action="store_true")
    add_format_argument(next_parser)
    next_parser.set_defaults(func=cmd_next)

    claim_parser = sub.add_parser("claim", help="claim a specific issue")
    claim_parser.add_argument("issue_id")
    claim_parser.add_argument("--owner")
    add_format_argument(claim_parser)
    claim_parser.set_defaults(func=cmd_claim)

    show_parser = sub.add_parser("show", help="show one issue")
    show_parser.add_argument("issue_id")
    show_parser.add_argument("--history", action="store_true")
    show_parser.add_argument("--field", action="append")
    show_parser.set_defaults(func=cmd_show)

    update_parser = sub.add_parser("update", help="update issue fields")
    update_parser.add_argument("issue_id")
    update_parser.add_argument("--title")
    update_parser.add_argument("--body")
    update_parser.add_argument("--state", choices=STATE_ORDER)
    update_parser.add_argument("--status", choices=STATE_ORDER)
    update_parser.add_argument("--owner")
    update_parser.add_argument("--label", action="append")
    update_parser.add_argument("--priority", type=int)
    update_parser.set_defaults(func=cmd_update)

    dep_parser = sub.add_parser("dep", help="add dependencies")
    dep_parser.add_argument("issue_id")
    dep_parser.add_argument("dep_ids", nargs="+")
    dep_parser.set_defaults(func=cmd_dep)

    close_parser = sub.add_parser("close", help="move an issue to the closed state")
    close_parser.add_argument("issue_id")
    close_parser.set_defaults(func=cmd_close)

    note_parser = sub.add_parser("note", help="append a note to an issue history")
    note_parser.add_argument("issue_id")
    note_parser.add_argument("text")
    note_parser.add_argument("--actor")
    note_parser.set_defaults(func=cmd_note)

    history_parser = sub.add_parser("history", help="show per-issue event history")
    history_parser.add_argument("issue_id")
    history_parser.add_argument("--format", choices=("text", "json"), default="text")
    history_parser.add_argument("--limit", type=int)
    history_parser.set_defaults(func=cmd_history)

    export_parser = sub.add_parser("export", help="export an issue to a visible scratch path")
    export_parser.add_argument("issue_id")
    export_parser.add_argument("--output")
    export_parser.set_defaults(func=cmd_export)

    import_parser = sub.add_parser("import", help="import an issue from a visible scratch path")
    import_parser.add_argument("issue_id")
    import_parser.add_argument("--input")
    import_parser.set_defaults(func=cmd_import)

    log_parser = sub.add_parser("log", help="show git history for an issue file")
    log_parser.add_argument("issue_id")
    log_parser.set_defaults(func=cmd_log)

    summary_parser = sub.add_parser("summary", help="print compact state counts")
    summary_parser.set_defaults(func=cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except StaleTrackerError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2
