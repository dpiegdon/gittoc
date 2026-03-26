from __future__ import annotations

import argparse
import json

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


def select_fields(data: dict, fields: list[str] | None) -> dict:
    if not fields:
        return data
    selected: dict = {}
    for field in fields:
        if field in data:
            selected[field] = data[field]
    return selected


def format_history_entry(entry: dict) -> str:
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
    data = issue.to_display(path.relative_to(tracker.checkout), tracker.note_count(issue.issue_id))
    data["ready"] = tracker.ready(issue)
    if reason:
        data["selection"] = reason
    notes = tracker.filtered_events(
        issue.issue_id, kinds={"note"}, limit=notes_limit
    )
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
    marker = ">" if data["ready"] else "*"
    owner = f" owner={data['owner']}" if data["owner"] else ""
    deps = f" deps={len(data['deps'])}" if data["deps"] else ""
    selection = f" selection={data['selection']}" if data.get("selection") else ""
    print(f"{marker} {data['id']} p{data['priority']} [{data['state']}] {data['title']}{deps}{owner}{selection}")
    if data["body"]:
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


def cmd_init(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    if not tracker.configured_remote():
        inferred = tracker.effective_remote()
        if inferred:
            tracker.configure_remote(inferred)
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


def cmd_remote(args: argparse.Namespace) -> int:
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
    tracker = Tracker.open()
    status = tracker.pull_remote(args.remote)
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"pulled {TRACKER_BRANCH} from {status['remote']} to {status['head']}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    tracker = Tracker.open()
    status = tracker.push_remote(args.remote)
    if args.format == "json":
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(f"pushed {TRACKER_BRANCH} to {status['remote']} at {status['head']}")
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
    ready_args = argparse.Namespace(all=False, state=None, ready_only=True, format=args.format)
    return cmd_list(ready_args)


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
    recent_notes = tracker.filtered_events(issue.issue_id, kinds={"note"}, limit=SHOW_NOTES_LIMIT)
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
    kinds = set(args.kind or [])
    if args.notes_only:
        kinds.add("note")
    entries = tracker.filtered_events(args.issue_id, kinds=kinds or None, limit=args.limit)
    if args.format == "json":
        print(json.dumps(entries, indent=2, sort_keys=True))
        return 0
    for entry in entries:
        print(format_history_entry(entry))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
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


def add_format_argument(parser: argparse.ArgumentParser, default: str = "normal") -> None:
    parser.add_argument(
        "--format",
        choices=("compact", "normal", "verbose", "json"),
        default=default,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skills/gittoc/gittoc")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="initialize tracker worktree")
    init_parser.set_defaults(func=cmd_init)

    refresh_parser = sub.add_parser("refresh", help="reload tracker state after conflicts")
    refresh_parser.add_argument("--format", choices=("text", "json"), default="text")
    refresh_parser.set_defaults(func=cmd_refresh)

    remote_parser = sub.add_parser("remote", help="show or configure tracker remote wiring")
    remote_parser.add_argument("--set")
    remote_parser.add_argument("--auto", action="store_true")
    remote_parser.add_argument("--format", choices=("text", "json"), default="text")
    remote_parser.set_defaults(func=cmd_remote)

    pull_parser = sub.add_parser("pull", help="fetch and merge the tracker branch from a remote")
    pull_parser.add_argument("remote")
    pull_parser.add_argument("--format", choices=("text", "json"), default="text")
    pull_parser.set_defaults(func=cmd_pull)

    push_parser = sub.add_parser("push", help="push the tracker branch to a remote")
    push_parser.add_argument("remote")
    push_parser.add_argument("--format", choices=("text", "json"), default="text")
    push_parser.set_defaults(func=cmd_push)

    new_parser = sub.add_parser("new", help="create an issue")
    new_parser.add_argument("title")
    new_parser.add_argument("--body")
    new_parser.add_argument("--label", action="append")
    new_parser.add_argument("--priority", type=int, default=DEFAULT_PRIORITY)
    new_parser.set_defaults(func=cmd_new)

    list_parser = sub.add_parser("list", help="list issues ordered by priority")
    list_parser.add_argument("--state", action="append", choices=STATE_ORDER)
    list_parser.add_argument("-a", "--all", action="store_true")
    list_parser.add_argument("--ready-only", action="store_true")
    add_format_argument(list_parser)
    list_parser.set_defaults(func=cmd_list)

    ready_parser = sub.add_parser("ready", help="list ready open issues by priority")
    add_format_argument(ready_parser)
    ready_parser.set_defaults(func=cmd_ready)

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
    history_parser.add_argument("--kind", action="append")
    history_parser.add_argument("--notes-only", action="store_true")
    history_parser.set_defaults(func=cmd_history)

    resume_parser = sub.add_parser(
        "resume", help="show compact recovery context for a specific or inferred issue"
    )
    resume_parser.add_argument("issue_id", nargs="?")
    resume_parser.add_argument("--owner")
    resume_parser.add_argument("--notes-limit", type=int, default=3)
    resume_parser.add_argument("--events-limit", type=int, default=3)
    resume_parser.add_argument("--format", choices=("text", "json"), default="text")
    resume_parser.set_defaults(func=cmd_resume)

    log_parser = sub.add_parser("log", help="show git history for an issue file")
    log_parser.add_argument("issue_id")
    log_parser.set_defaults(func=cmd_log)

    summary_parser = sub.add_parser("summary", help="print compact state counts")
    summary_parser.set_defaults(func=cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
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
