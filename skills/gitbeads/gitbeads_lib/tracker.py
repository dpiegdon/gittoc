from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

from .common import (
    EVENT_SUFFIX,
    EXPORT_ROOT,
    ISSUES_ROOT,
    LEGACY_HEAD_STORE,
    STATE_ORDER,
    STATE_SET,
    TRACKER_BRANCH,
    branch_exists,
    current_branch,
    default_owner,
    has_legacy_hidden_clone,
    is_worktree,
    issue_number,
    now_utc,
    parse_state,
    repo_root,
    run_git,
    validate_issue_id,
    validate_priority,
    worktree_path,
)
from .models import Issue


class StaleTrackerError(SystemExit):
    pass


class Tracker:
    def __init__(self, repo: Path, checkout: Path):
        self.repo = repo
        self.checkout = checkout
        self.base_head = self.head()

    @classmethod
    def open(cls) -> "Tracker":
        repo = repo_root()
        checkout = cls._ensure_worktree(repo)
        tracker = cls(repo, checkout)
        tracker.migrate_layout()
        tracker.base_head = tracker.head()
        return tracker

    @staticmethod
    def _ensure_worktree(repo: Path) -> Path:
        checkout = worktree_path(repo)
        if has_legacy_hidden_clone(checkout):
            raise SystemExit(
                f"legacy hidden clone detected at {checkout}; remove it before using worktree mode"
            )
        if is_worktree(checkout):
            if current_branch(checkout) != TRACKER_BRANCH:
                run_git(["switch", "-q", TRACKER_BRANCH], cwd=checkout)
            return checkout
        if branch_exists(repo, TRACKER_BRANCH):
            run_git(["worktree", "add", "--force", str(checkout), TRACKER_BRANCH], cwd=repo)
            return checkout
        return Tracker._bootstrap_worktree(repo, checkout)

    @staticmethod
    def _bootstrap_worktree(repo: Path, checkout: Path) -> Path:
        run_git(["worktree", "add", "--detach", "--force", str(checkout), "HEAD"], cwd=repo)
        run_git(["checkout", "-q", "--orphan", TRACKER_BRANCH], cwd=checkout)
        run_git(["rm", "-rf", "--cached", "."], cwd=checkout, check=False)
        for path in checkout.iterdir():
            if path.name == ".git":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        imported = False
        proc = run_git(
            ["ls-tree", "-r", "--name-only", "HEAD", str(LEGACY_HEAD_STORE)],
            cwd=repo,
            check=False,
        )
        for rel_name in proc.stdout.splitlines():
            rel_name = rel_name.strip()
            if not rel_name.endswith(".json"):
                continue
            data = run_git(["show", f"HEAD:{rel_name}"], cwd=repo).stdout
            target = checkout / ISSUES_ROOT / "open" / Path(rel_name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data, encoding="utf-8")
            imported = True
        if not imported:
            for state in STATE_ORDER:
                (checkout / ISSUES_ROOT / state).mkdir(parents=True, exist_ok=True)
            keep = checkout / ISSUES_ROOT / ".gitkeep"
            keep.write_text("", encoding="utf-8")
        run_git(["add", "issues"], cwd=checkout)
        run_git(
            ["commit", "-q", "-m", "Import legacy gitbeads issues" if imported else "Initialize gitbeads tracker"],
            cwd=checkout,
        )
        return checkout

    def head(self) -> str:
        proc = run_git(["rev-parse", "--verify", "HEAD"], cwd=self.checkout, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def refresh(self) -> str:
        self.base_head = self.head()
        return self.base_head

    def ensure_not_stale(self) -> None:
        current = self.head()
        if current != self.base_head:
            raise StaleTrackerError(
                "tracker changed during this command; run `skills/gitbeads/gitbeads refresh` and retry"
            )

    def issues_root(self) -> Path:
        return self.checkout / ISSUES_ROOT

    def state_dir(self, state: str) -> Path:
        if state not in STATE_SET:
            raise SystemExit(f"invalid state: {state}")
        return self.issues_root() / state

    def issue_path(self, issue_id: str, state: str) -> Path:
        return self.state_dir(state) / f"{validate_issue_id(issue_id)}.json"

    def event_path(self, issue_id: str, state: str) -> Path:
        return self.state_dir(state) / f"{validate_issue_id(issue_id)}{EVENT_SUFFIX}"

    def find_issue_path(self, issue_id: str) -> Path:
        issue_id = validate_issue_id(issue_id)
        for state in STATE_ORDER:
            path = self.issue_path(issue_id, state)
            if path.exists():
                return path
        raise SystemExit(f"issue not found: {issue_id}")

    def find_event_path(self, issue_id: str) -> Path | None:
        issue_id = validate_issue_id(issue_id)
        for state in STATE_ORDER:
            path = self.event_path(issue_id, state)
            if path.exists():
                return path
        return None

    def commit_if_needed(self, message: str) -> None:
        proc = run_git(["status", "--porcelain", "--", "issues"], cwd=self.checkout)
        if not proc.stdout.strip():
            return
        self.ensure_not_stale()
        run_git(["add", "issues"], cwd=self.checkout)
        run_git(["commit", "-q", "-m", message], cwd=self.checkout)
        self.base_head = self.head()

    def write_issue(self, issue: Issue, previous_path: Path | None = None) -> Path:
        path = self.issue_path(issue.issue_id, issue.state)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(issue.to_record(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if previous_path and previous_path != path and previous_path.exists():
            previous_path.unlink()
        return path

    def move_event_file(self, issue_id: str, new_state: str, previous_path: Path | None) -> None:
        if not previous_path:
            return
        previous_event = previous_path.with_name(previous_path.stem + EVENT_SUFFIX)
        if not previous_event.exists():
            return
        target = self.event_path(issue_id, new_state)
        target.parent.mkdir(parents=True, exist_ok=True)
        if previous_event != target:
            previous_event.rename(target)

    def append_event(
        self, issue: Issue, kind: str, text: str = "", actor: str | None = None
    ) -> None:
        path = self.event_path(issue.issue_id, issue.state)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "actor": actor or default_owner(),
            "at": now_utc(),
            "kind": kind,
            "text": text,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def event_entries(self, issue_id: str) -> list[dict]:
        path = self.find_event_path(issue_id)
        if not path or not path.exists():
            return []
        entries: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def note_count(self, issue_id: str) -> int:
        return sum(1 for entry in self.event_entries(issue_id) if entry["kind"] == "note")

    def migrate_layout(self) -> None:
        for state in STATE_ORDER:
            self.state_dir(state).mkdir(parents=True, exist_ok=True)
        changed = False
        for path in sorted(self.issues_root().rglob("GB-*.json")):
            if path.name.endswith(EVENT_SUFFIX):
                continue
            issue = Issue.from_path(path)
            canonical = self.issue_path(issue.issue_id, issue.state)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            desired = json.dumps(issue.to_record(), indent=2, sort_keys=True) + "\n"
            current = canonical.read_text(encoding="utf-8") if canonical.exists() else ""
            if current != desired:
                canonical.write_text(desired, encoding="utf-8")
                changed = True
            if path != canonical and path.exists():
                path.unlink()
                changed = True
            legacy_event = path.with_name(path.stem + EVENT_SUFFIX)
            canonical_event = canonical.with_name(canonical.stem + EVENT_SUFFIX)
            if legacy_event.exists() and legacy_event != canonical_event:
                canonical_event.parent.mkdir(parents=True, exist_ok=True)
                legacy_event.rename(canonical_event)
                changed = True
        for path in sorted(self.issues_root().rglob("*"), reverse=True):
            if (
                path.exists()
                and path.is_dir()
                and path != self.issues_root()
                and not any(path.iterdir())
            ):
                try:
                    path.rmdir()
                except FileNotFoundError:
                    pass
        if changed:
            self.commit_if_needed("Migrate gitbeads issue layout")

    def next_issue_id(self) -> str:
        highest = 0
        for path in self.issues_root().rglob("GB-*.json"):
            if path.name.endswith(EVENT_SUFFIX):
                continue
            highest = max(highest, issue_number(path.stem))
        return f"GB-{highest + 1}"

    def issue_paths(self, states: tuple[str, ...] | None = None) -> list[Path]:
        states = states or ("open",)
        paths: list[Path] = []
        for state in states:
            paths.extend(
                sorted(
                    (
                        path
                        for path in self.state_dir(state).glob("GB-*.json")
                        if not path.name.endswith(EVENT_SUFFIX)
                    ),
                    key=lambda path: issue_number(path.stem),
                )
            )
        return paths

    def sort_key(self, issue: Issue) -> tuple[int, int, int]:
        return (issue.priority, STATE_ORDER.index(issue.state), issue_number(issue.issue_id))

    def list_issues(self, states: tuple[str, ...] | None = None) -> list[Issue]:
        return sorted([Issue.from_path(path) for path in self.issue_paths(states)], key=self.sort_key)

    def load_issue(self, issue_id: str) -> tuple[Issue, Path]:
        path = self.find_issue_path(issue_id)
        return Issue.from_path(path), path

    def create_issue(
        self, title: str, body: str, labels: list[str], priority: int, state: str = "open"
    ) -> Issue:
        timestamp = now_utc()
        issue = Issue(
            issue_id=self.next_issue_id(),
            title=title,
            body=body,
            deps=(),
            labels=tuple(labels),
            owner="",
            priority=validate_priority(priority),
            created_at=timestamp,
            updated_at=timestamp,
            state=state,
        )
        self.write_issue(issue)
        self.append_event(issue, "created", issue.title)
        self.commit_if_needed(f"Add issue {issue.issue_id}: {issue.title}")
        return issue

    def dependency_closed(self, issue_id: str) -> bool:
        dep, _ = self.load_issue(issue_id)
        return dep.state == "closed"

    def ready(self, issue: Issue) -> bool:
        return issue.state == "open" and all(self.dependency_closed(dep_id) for dep_id in issue.deps)

    def ready_issues(self) -> list[Issue]:
        return sorted([issue for issue in self.list_issues(("open",)) if self.ready(issue)], key=self.sort_key)

    def summary(self) -> dict[str, int]:
        counts = {state: 0 for state in STATE_ORDER}
        ready = 0
        for issue in self.list_issues(STATE_ORDER):
            counts[issue.state] += 1
            if self.ready(issue):
                ready += 1
        counts["ready"] = ready
        return counts

    def update_issue(
        self,
        issue_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        owner: str | None = None,
        labels: list[str] | None = None,
        priority: int | None = None,
        message: str | None = None,
        event_kind: str = "updated",
        event_text: str = "",
        event_actor: str | None = None,
    ) -> Issue:
        issue, path = self.load_issue(issue_id)
        updated = replace(
            issue,
            title=issue.title if title is None else title,
            body=issue.body if body is None else body,
            state=issue.state if state is None else state,
            owner=issue.owner if owner is None else owner,
            labels=issue.labels if labels is None else tuple(labels),
            priority=issue.priority if priority is None else validate_priority(priority),
            updated_at=now_utc(),
        )
        self.move_event_file(updated.issue_id, updated.state, path)
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, event_kind, event_text, actor=event_actor)
        self.commit_if_needed(message or f"Update issue {updated.issue_id}")
        return updated

    def set_dependencies(self, issue_id: str, dep_ids: list[str]) -> Issue:
        issue, path = self.load_issue(issue_id)
        deps = set(issue.deps)
        for dep_id in dep_ids:
            dep = validate_issue_id(dep_id)
            self.find_issue_path(dep)
            deps.add(dep)
        updated = replace(issue, deps=tuple(sorted(deps, key=issue_number)), updated_at=now_utc())
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, "dependency", " ".join(dep_ids))
        self.commit_if_needed(f"Add dependencies to {updated.issue_id}")
        return updated

    def add_note(self, issue_id: str, text: str, actor: str | None = None) -> Issue:
        issue, path = self.load_issue(issue_id)
        updated = replace(issue, updated_at=now_utc())
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, "note", text, actor=actor)
        self.commit_if_needed(f"Add note to {updated.issue_id}")
        return updated

    def export_issue(self, issue_id: str, output: Path | None = None) -> Path:
        issue, path = self.load_issue(issue_id)
        export_dir = self.repo / EXPORT_ROOT
        export_dir.mkdir(parents=True, exist_ok=True)
        output = output or (export_dir / f"{issue.issue_id}.json")
        payload = issue.to_display(path.relative_to(self.checkout), self.note_count(issue.issue_id))
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.append_event(issue, "exported", str(output.relative_to(self.repo)))
        self.commit_if_needed(f"Export issue {issue.issue_id}")
        return output

    def import_issue(self, issue_id: str, input_path: Path | None = None) -> Issue:
        issue, path = self.load_issue(issue_id)
        source = input_path or (self.repo / EXPORT_ROOT / f"{issue.issue_id}.json")
        data = json.loads(source.read_text(encoding="utf-8"))
        if validate_issue_id(data["id"]) != issue.issue_id:
            raise SystemExit("import file issue id does not match target issue")
        updated = replace(
            issue,
            title=data.get("title", issue.title),
            body=data.get("body", issue.body),
            deps=tuple(sorted(set(data.get("deps", list(issue.deps))), key=issue_number)),
            labels=tuple(data.get("labels", list(issue.labels))),
            owner=data.get("owner", issue.owner),
            priority=validate_priority(int(data.get("priority", issue.priority))),
            state=parse_state(data.get("state")) or issue.state,
            updated_at=now_utc(),
        )
        self.move_event_file(updated.issue_id, updated.state, path)
        self.write_issue(updated, previous_path=path)
        rel = source.relative_to(self.repo) if source.is_relative_to(self.repo) else source
        self.append_event(updated, "imported", str(rel))
        self.commit_if_needed(f"Import issue {updated.issue_id}")
        return updated

