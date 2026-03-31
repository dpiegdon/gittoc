"""Core tracker logic: worktree management, issue storage, and state transitions."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .common import (
    EVENT_SUFFIX,
    ISSUES_ROOT,
    STATE_ORDER,
    STATE_SET,
    TERMINAL_STATES,
    TRACKER_BRANCH,
    branch_exists,
    current_branch,
    default_owner,
    has_legacy_hidden_clone,
    infer_remote,
    is_worktree,
    issue_number,
    list_remotes,
    local_config_get,
    local_config_set,
    now_utc,
    remote_branch_exists,
    repo_root,
    run_git,
    validate_issue_id,
    validate_priority,
    worktree_path,
)
from .models import Issue


class StaleTrackerError(Exception):
    """Raised when the tracker has been modified since it was opened."""


class Tracker:
    """Manages the gittoc issue store on the dedicated tracker branch."""

    def __init__(self, repo: Path, checkout: Path):
        """Initialise with repo root and tracker worktree paths."""
        self.repo = repo
        self.checkout = checkout
        self.base_head = self.head()

    @classmethod
    def open(cls) -> "Tracker":
        """Open the tracker, ensuring the worktree exists and running migrations."""
        repo = repo_root()
        checkout = cls._ensure_worktree(repo)
        tracker = cls(repo, checkout)
        tracker.run_pending_migrations()
        tracker.base_head = tracker.head()
        return tracker

    @staticmethod
    def _ensure_worktree(repo: Path) -> Path:
        """Ensure the hidden gittoc worktree exists, creating or attaching it as needed."""
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
            run_git(
                ["worktree", "add", "--force", str(checkout), TRACKER_BRANCH], cwd=repo
            )
            return checkout
        remote = infer_remote(repo)
        if remote and remote_branch_exists(repo, remote, TRACKER_BRANCH):
            run_git(
                ["branch", "--track", TRACKER_BRANCH, f"{remote}/{TRACKER_BRANCH}"],
                cwd=repo,
            )
            run_git(
                ["worktree", "add", "--force", str(checkout), TRACKER_BRANCH], cwd=repo
            )
            return checkout
        return Tracker._bootstrap_worktree(repo, checkout)

    @staticmethod
    def _bootstrap_worktree(repo: Path, checkout: Path) -> Path:
        """Create an orphan tracker branch with an empty issues directory structure."""
        # git worktree add requires at least one commit; create one if the repo is empty.
        proc = run_git(["rev-parse", "--verify", "HEAD"], cwd=repo, check=False)
        if proc.returncode != 0:
            run_git(["commit", "--allow-empty", "-q", "-m", "Initial commit"], cwd=repo)
        run_git(
            ["worktree", "add", "--detach", "--force", str(checkout), "HEAD"], cwd=repo
        )
        run_git(["checkout", "-q", "--orphan", TRACKER_BRANCH], cwd=checkout)
        run_git(["rm", "-rf", "--cached", "."], cwd=checkout, check=False)
        for path in checkout.iterdir():
            if path.name == ".git":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        for state in STATE_ORDER:
            (checkout / ISSUES_ROOT / state).mkdir(parents=True, exist_ok=True)
        keep = checkout / ISSUES_ROOT / ".gitkeep"
        keep.write_text("", encoding="utf-8")
        run_git(["add", "issues"], cwd=checkout)
        run_git(
            ["commit", "-q", "-m", "Initialize gittoc tracker"],
            cwd=checkout,
        )
        return checkout

    def head(self) -> str:
        """Return the current HEAD commit hash of the tracker branch."""
        proc = run_git(
            ["rev-parse", "--verify", "HEAD"], cwd=self.checkout, check=False
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def configured_remote(self) -> str:
        """Return the explicitly configured tracker remote, or empty string."""
        return local_config_get(self.repo, "gittoc.remote")

    def effective_remote(self) -> str:
        """Return the configured remote, falling back to the inferred one."""
        return self.configured_remote() or infer_remote(self.repo)

    def remote_status(self) -> dict[str, object]:
        """Return a dict describing the current remote wiring state."""
        configured = self.configured_remote()
        inferred = infer_remote(self.repo)
        effective = configured or inferred
        branch_remote = local_config_get(self.repo, f"branch.{TRACKER_BRANCH}.remote")
        branch_merge = local_config_get(self.repo, f"branch.{TRACKER_BRANCH}.merge")
        return {
            "remotes": list_remotes(self.repo),
            "inferred_remote": inferred,
            "configured_remote": configured,
            "effective_remote": effective,
            "tracker_branch": TRACKER_BRANCH,
            "branch_config_remote": branch_remote,
            "branch_config_merge": branch_merge,
            "remote_branch_exists": bool(
                effective and remote_branch_exists(self.repo, effective, TRACKER_BRANCH)
            ),
        }

    def configure_remote(self, remote: str) -> dict[str, object]:
        """Configure the tracker branch to use the given remote and return status."""
        if remote not in list_remotes(self.repo):
            raise SystemExit(f"unknown remote: {remote}")
        local_config_set(self.repo, "gittoc.remote", remote)
        local_config_set(self.repo, f"branch.{TRACKER_BRANCH}.remote", remote)
        local_config_set(
            self.repo, f"branch.{TRACKER_BRANCH}.merge", f"refs/heads/{TRACKER_BRANCH}"
        )
        return self.remote_status()

    def _validate_remote(self, remote: str) -> None:
        """Raise SystemExit if remote is not a known git remote."""
        if remote not in list_remotes(self.repo):
            raise SystemExit(f"unknown remote: {remote}")

    def pull_remote(self, remote: str) -> dict[str, str]:
        """Fetch and merge the tracker branch from the given remote."""
        self._validate_remote(remote)
        run_git(["fetch", remote, TRACKER_BRANCH], cwd=self.repo)
        if not remote_branch_exists(self.repo, remote, TRACKER_BRANCH):
            raise SystemExit(f"remote branch not found: {remote}/{TRACKER_BRANCH}")
        proc = run_git(
            ["merge", "--no-edit", f"{remote}/{TRACKER_BRANCH}"],
            cwd=self.checkout,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(
                f"pull failed while merging {remote}/{TRACKER_BRANCH}; resolve conflicts in {self.checkout} and re-run your command"
            )
        self.base_head = self.head()
        return {"action": "pull", "remote": remote, "head": self.base_head}

    def push_remote(self, remote: str) -> dict[str, str]:
        """Push the tracker branch to the given remote."""
        self._validate_remote(remote)
        try:
            run_git(
                ["push", remote, f"{TRACKER_BRANCH}:{TRACKER_BRANCH}"], cwd=self.repo
            )
        except subprocess.CalledProcessError as exc:
            raise SystemExit(
                f"push failed for {remote}/{TRACKER_BRANCH}: {exc.stderr.strip() or exc.stdout.strip()}"
            ) from exc
        self.base_head = self.head()
        return {"action": "push", "remote": remote, "head": self.base_head}

    def ensure_not_stale(self) -> None:
        """Raise StaleTrackerError if the tracker has been modified since it was opened."""
        current = self.head()
        if current != self.base_head:
            raise StaleTrackerError(
                "tracker changed during this command; re-run your command to retry"
            )

    def issues_root(self) -> Path:
        """Return the path to the issues root directory in the tracker worktree."""
        return self.checkout / ISSUES_ROOT

    def state_dir(self, state: str) -> Path:
        """Return the directory path for a given issue state, raising on invalid state."""
        if state not in STATE_SET:
            raise SystemExit(f"invalid state: {state}")
        return self.issues_root() / state

    def issue_path(self, issue_id: str, state: str) -> Path:
        """Return the expected JSON file path for an issue in the given state."""
        return self.state_dir(state) / f"{validate_issue_id(issue_id)}.json"

    def event_path(self, issue_id: str, state: str) -> Path:
        """Return the expected event log path for an issue in the given state."""
        return self.state_dir(state) / f"{validate_issue_id(issue_id)}{EVENT_SUFFIX}"

    def find_issue_path(self, issue_id: str) -> Path:
        """Search all state directories and return the path where the issue lives."""
        issue_id = validate_issue_id(issue_id)
        for state in STATE_ORDER:
            path = self.issue_path(issue_id, state)
            if path.exists():
                return path
        raise SystemExit(f"issue not found: {issue_id}")

    def find_event_path(self, issue_id: str) -> Path | None:
        """Return the event log path for an issue, or None if no log exists yet."""
        issue_id = validate_issue_id(issue_id)
        for state in STATE_ORDER:
            path = self.event_path(issue_id, state)
            if path.exists():
                return path
        return None

    def commit_if_needed(self, message: str, actor: str | None = None) -> None:
        """Stage and commit any pending changes to the issues tree, if any exist."""
        proc = run_git(["status", "--porcelain", "--", "issues"], cwd=self.checkout)
        if not proc.stdout.strip():
            return
        self.ensure_not_stale()
        run_git(["add", "issues"], cwd=self.checkout)
        commit_actor = actor or default_owner()
        run_git(
            ["commit", "-q", "-m", f"{message} ({commit_actor})"], cwd=self.checkout
        )
        self.base_head = self.head()

    def write_issue(self, issue: Issue, previous_path: Path | None = None) -> Path:
        """Write the issue JSON to disk, removing the old path if it has moved."""
        path = self.issue_path(issue.issue_id, issue.state)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(issue.to_record(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if previous_path and previous_path != path and previous_path.exists():
            previous_path.unlink()
        return path

    def move_event_file(
        self, issue_id: str, new_state: str, previous_path: Path | None
    ) -> None:
        """Relocate the event log alongside the issue when its state directory changes."""
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
        """Append a timestamped event entry to the issue's event log."""
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
        """Return all event log entries for an issue, in chronological order."""
        path = self.find_event_path(issue_id)
        if not path or not path.exists():
            return []
        entries: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(
                        f"warning: skipping malformed event at {path}:{lineno}",
                        file=sys.stderr,
                    )
        return entries

    def filtered_events(
        self,
        issue_id: str,
        *,
        kinds: set[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Return event entries filtered by kind and/or capped at limit (most recent)."""
        entries = self.event_entries(issue_id)
        if kinds:
            entries = [entry for entry in entries if entry.get("kind") in kinds]
        if limit is not None:
            entries = entries[-limit:]
        return entries

    def note_count(self, issue_id: str) -> int:
        """Return the number of note events recorded for an issue."""
        return sum(
            1 for entry in self.event_entries(issue_id) if entry["kind"] == "note"
        )

    def run_pending_migrations(self) -> None:
        """Hook for future tracker migrations.

        The current on-disk layout is the baseline, so normal tracker startup
        should not rewrite issue state. Add explicit migration steps here only
        when a future storage change requires them.
        """

    def next_issue_id(self) -> str:
        """Scan existing issue files and return the next unused T-<n> identifier."""
        highest = 0
        for path in self.issues_root().rglob("T-*.json"):
            if path.name.endswith(EVENT_SUFFIX):
                continue
            highest = max(highest, issue_number(path.stem))
        return f"T-{highest + 1}"

    def issue_paths(self, states: tuple[str, ...] | None = None) -> list[Path]:
        """Return sorted JSON file paths for issues in the given states (default: open)."""
        states = states or ("open",)
        paths: list[Path] = []
        for state in states:
            paths.extend(
                sorted(
                    (
                        path
                        for path in self.state_dir(state).glob("T-*.json")
                        if not path.name.endswith(EVENT_SUFFIX)
                    ),
                    key=lambda path: issue_number(path.stem),
                )
            )
        return paths

    def sort_key(self, issue: Issue) -> tuple[int, int, int]:
        """Return a (priority, state-order, issue-number) tuple for consistent sorting."""
        return (
            issue.priority,
            STATE_ORDER.index(issue.state),
            issue_number(issue.issue_id),
        )

    def list_issues(self, states: tuple[str, ...] | None = None) -> list[Issue]:
        """Load and return issues in the given states, sorted by priority."""
        return sorted(
            [Issue.from_path(path) for path in self.issue_paths(states)],
            key=self.sort_key,
        )

    def load_issue(self, issue_id: str) -> tuple[Issue, Path]:
        """Load an issue by ID and return it together with its file path."""
        path = self.find_issue_path(issue_id)
        return Issue.from_path(path), path

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str],
        priority: int,
        state: str = "open",
    ) -> Issue:
        """Create a new issue, write it to disk, append a created event, and commit."""
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
        """Return True if the named dependency issue is in a terminal state."""
        dep, _ = self.load_issue(issue_id)
        return dep.state in TERMINAL_STATES

    def ready(self, issue: Issue) -> bool:
        """Return True if the issue is open and all its dependencies are closed."""
        return issue.state == "open" and all(
            self.dependency_closed(dep_id) for dep_id in issue.deps
        )

    def _would_introduce_cycle(self, issue_id: str, dep_id: str) -> bool:
        """Return True if adding dep_id as a dependency of issue_id would create a cycle."""
        if dep_id == issue_id:
            return True
        seen: set[str] = set()
        stack = [dep_id]
        while stack:
            current = stack.pop()
            if current == issue_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            current_issue, _ = self.load_issue(current)
            stack.extend(current_issue.deps)
        return False

    def ready_issues(self) -> list[Issue]:
        """Return all open issues with no unresolved dependencies, sorted by priority."""
        return sorted(
            [issue for issue in self.list_issues(("open",)) if self.ready(issue)],
            key=self.sort_key,
        )

    def resume_issue(self, owner: str) -> tuple[Issue | None, str | None]:
        """Select the best issue to resume: owner's claimed > ready > open."""
        mine = [
            issue for issue in self.list_issues(("claimed",)) if issue.owner == owner
        ]
        if mine:
            return mine[0], "claimed-by-owner"
        ready = self.ready_issues()
        if ready:
            return ready[0], "highest-priority-ready"
        open_issues = self.list_issues(("open",))
        if open_issues:
            return open_issues[0], "highest-priority-open"
        return None, None

    def summary(self) -> dict[str, int]:
        """Return a dict of issue counts per state plus a 'ready' count."""
        counts = {state: 0 for state in STATE_ORDER}
        all_issues = self.list_issues(STATE_ORDER)
        closed_ids = {i.issue_id for i in all_issues if i.state in TERMINAL_STATES}
        ready = 0
        for issue in all_issues:
            counts[issue.state] += 1
            if issue.state == "open" and all(dep in closed_ids for dep in issue.deps):
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
        """Apply one or more field changes to an issue and commit the result."""
        issue, path = self.load_issue(issue_id)
        target_state = issue.state if state is None else state
        if target_state == "claimed" and issue.state != "claimed":
            if issue.state != "open":
                raise SystemExit(
                    f"cannot claim issue from state {issue.state}: {issue.issue_id}"
                )
            if not self.ready(issue):
                raise SystemExit(f"cannot claim non-ready issue: {issue.issue_id}")
        updated = replace(
            issue,
            title=issue.title if title is None else title,
            body=issue.body if body is None else body,
            state=target_state,
            owner=issue.owner if owner is None else owner,
            labels=issue.labels if labels is None else tuple(labels),
            priority=(
                issue.priority if priority is None else validate_priority(priority)
            ),
            updated_at=now_utc(),
        )
        self.move_event_file(updated.issue_id, updated.state, path)
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, event_kind, event_text, actor=event_actor)
        self.commit_if_needed(
            message or f"Update issue {updated.issue_id}", actor=event_actor
        )
        return updated

    def reject_issue(self, issue_id: str, *, actor: str | None = None) -> Issue:
        """Move an issue to the rejected state (won't-do / abandoned)."""
        return self.update_issue(
            issue_id,
            state="rejected",
            message=f"Reject issue {issue_id}",
            event_kind="rejected",
            event_actor=actor,
        )

    def set_dependencies(self, issue_id: str, dep_ids: list[str]) -> Issue:
        """Add blocking dependencies to an issue, rejecting cycles."""
        issue, path = self.load_issue(issue_id)
        deps = set(issue.deps)
        for dep_id in dep_ids:
            dep = validate_issue_id(dep_id)
            self.find_issue_path(dep)
            if self._would_introduce_cycle(issue.issue_id, dep):
                raise SystemExit(
                    f"dependency would introduce a cycle: {issue.issue_id} -> {dep}"
                )
            deps.add(dep)
        updated = replace(
            issue, deps=tuple(sorted(deps, key=issue_number)), updated_at=now_utc()
        )
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, "dependency", " ".join(dep_ids))
        self.commit_if_needed(f"Add dependencies to {updated.issue_id}")
        return updated

    def remove_dependencies(self, issue_id: str, dep_ids: list[str]) -> Issue:
        """Remove blocking dependencies from an issue."""
        issue, path = self.load_issue(issue_id)
        to_remove = set()
        for dep_id in dep_ids:
            validate_issue_id(dep_id)
            if dep_id not in issue.deps:
                raise SystemExit(
                    f"{dep_id} is not a dependency of {issue.issue_id}"
                )
            to_remove.add(dep_id)
        new_deps = tuple(d for d in issue.deps if d not in to_remove)
        updated = replace(issue, deps=new_deps, updated_at=now_utc())
        self.write_issue(updated, previous_path=path)
        self.append_event(updated, "dependency", f"removed {' '.join(dep_ids)}")
        self.commit_if_needed(f"Remove dependencies from {updated.issue_id}")
        return updated

    def add_note(self, issue_id: str, text: str, actor: str | None = None) -> Issue:
        """Append a free-text note event to an issue and commit."""
        issue, _ = self.load_issue(issue_id)
        self.append_event(issue, "note", text, actor=actor)
        self.commit_if_needed(f"Add note to {issue.issue_id}", actor=actor)
        return issue
