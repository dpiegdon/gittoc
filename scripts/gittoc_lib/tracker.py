"""Core tracker logic: worktree management, issue storage, and state transitions."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from . import CURRENT_FORMAT_VERSION, CURRENT_LAYOUT_VERSION, VERSION_FILE
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
from .integrity import (
    IntegrityFinding,
    IntegrityReport,
    issue_id_from_path,
    render_integrity_report,
)
from .models import Issue


class RemotePushPullError(Exception):
    """Raised when a push or pull fails due to a remote/network error."""


class StaleTrackerError(Exception):
    """Raised when the tracker has been modified since it was opened."""


class Tracker:
    """Manages the gittoc issue store on the dedicated tracker branch."""

    def __init__(self, repo: Path, checkout: Path):
        """Initialise with repo root and tracker worktree paths."""
        self.repo = repo
        self.checkout = checkout
        self.base_head = self.head()
        self._event_cache: dict[str, list[dict]] = {}
        self._state_cache: dict[str, str] = {}

    @classmethod
    def open(cls) -> "Tracker":
        """Open the tracker, ensuring the worktree exists and running migrations."""
        repo = repo_root()
        checkout = cls._ensure_worktree(repo)
        tracker = cls(repo, checkout)
        tracker.run_pending_migrations()
        tracker.check_version_compatible()
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
        version_path = checkout / VERSION_FILE
        version_data = {
            "format_version": CURRENT_FORMAT_VERSION,
            "layout_version": CURRENT_LAYOUT_VERSION,
            "migrated_at": now_utc(),
            "migrated_by": default_owner(),
        }
        with version_path.open("w", encoding="utf-8") as handle:
            json.dump(version_data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        run_git(["add", "issues", str(VERSION_FILE)], cwd=checkout)
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

    def read_version(self) -> tuple[int, int]:
        """Read the VERSION file and return (format_version, layout_version).

        Returns (0, 0) if the file does not exist (pre-versioning baseline).
        Raises SystemExit on malformed or unreadable VERSION files.
        """
        path = self.checkout / VERSION_FILE
        if not path.exists():
            return (0, 0)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return (data["format_version"], data["layout_version"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SystemExit(f"malformed VERSION file ({path}): {exc}") from exc

    def _write_version(
        self, format_version: int, layout_version: int, *, commit: bool = True
    ) -> None:
        """Write the VERSION file and optionally commit it."""
        path = self.checkout / VERSION_FILE
        data = {
            "format_version": format_version,
            "layout_version": layout_version,
            "migrated_at": now_utc(),
            "migrated_by": default_owner(),
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        if commit:
            run_git(["add", str(VERSION_FILE)], cwd=self.checkout)
            run_git(
                [
                    "commit",
                    "-q",
                    "-m",
                    f"gittoc: migrate to format v{format_version} layout v{layout_version}",
                ],
                cwd=self.checkout,
            )

    def check_version_compatible(self) -> None:
        """Abort if the local tracker version is newer than this client supports."""
        fmt, layout = self.read_version()
        if fmt > CURRENT_FORMAT_VERSION:
            raise SystemExit(
                f"tracker requires format version {fmt}, "
                f"but this gittoc only supports up to {CURRENT_FORMAT_VERSION} — "
                f"please upgrade gittoc"
            )
        if layout > CURRENT_LAYOUT_VERSION:
            raise SystemExit(
                f"tracker requires layout version {layout}, "
                f"but this gittoc only supports up to {CURRENT_LAYOUT_VERSION} — "
                f"please upgrade gittoc"
            )

    @staticmethod
    def read_remote_version(repo: Path, remote: str) -> tuple[int, int]:
        """Read the VERSION file from a remote tracking ref.

        Returns (0, 0) if the file does not exist on the remote.
        """
        proc = run_git(
            ["show", f"{remote}/{TRACKER_BRANCH}:{VERSION_FILE}"],
            cwd=repo,
            check=False,
        )
        if proc.returncode != 0:
            return (0, 0)
        try:
            data = json.loads(proc.stdout)
            return (data["format_version"], data["layout_version"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SystemExit(
                f"malformed VERSION on {remote}/{TRACKER_BRANCH}: {exc}"
            ) from exc

    @staticmethod
    def check_versions_match(
        local: tuple[int, int], remote: tuple[int, int], remote_name: str
    ) -> None:
        """Abort if local and remote versions differ (unless either is unset)."""
        if local == (0, 0) or remote == (0, 0):
            return
        if local != remote:
            raise SystemExit(
                f"version mismatch: local format v{local[0]} layout v{local[1]}, "
                f"but {remote_name} has format v{remote[0]} layout v{remote[1]} — "
                f"ensure all users are on the same gittoc version before syncing"
            )

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

    def _merge_kind(self, before_head: str, after_head: str) -> str:
        """Classify a pull result as unchanged, fast-forward, or merge."""
        if after_head == before_head:
            return "unchanged"
        proc = run_git(
            ["rev-list", "--parents", "-n", "1", after_head],
            cwd=self.checkout,
            check=False,
        )
        parent_count = max(len(proc.stdout.strip().split()) - 1, 0)
        return "merge" if parent_count > 1 else "fast-forward"

    def _pull_changed_paths(self, before_head: str, after_head: str) -> list[Path]:
        """Return tracker files changed by a pull, relative to the pre-pull HEAD."""
        if not before_head or after_head == before_head:
            return []
        proc = run_git(
            ["diff", "--name-only", before_head, after_head, "--", "issues"],
            cwd=self.checkout,
            check=False,
        )
        return [
            self.checkout / line.strip()
            for line in proc.stdout.splitlines()
            if line.strip()
        ]

    def pull_remote(self, remote: str) -> dict[str, object]:
        """Fetch and merge the tracker branch from the given remote."""
        self._validate_remote(remote)
        before_head = self.head()
        try:
            run_git(["fetch", remote, TRACKER_BRANCH], cwd=self.repo)
        except subprocess.CalledProcessError as exc:
            raise RemotePushPullError(
                f"pull failed for {remote}/{TRACKER_BRANCH}: "
                f"{exc.stderr.strip() or exc.stdout.strip()}"
            ) from exc
        if not remote_branch_exists(self.repo, remote, TRACKER_BRANCH):
            raise SystemExit(f"remote branch not found: {remote}/{TRACKER_BRANCH}")
        self.check_versions_match(
            self.read_version(),
            self.read_remote_version(self.repo, remote),
            f"{remote}/{TRACKER_BRANCH}",
        )
        proc = run_git(
            ["merge", "--no-edit", f"{remote}/{TRACKER_BRANCH}"],
            cwd=self.checkout,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(
                f"pull failed while merging {remote}/{TRACKER_BRANCH}; "
                f"resolve conflicts in {self.checkout} and re-run your command"
            )
        self.base_head = self.head()
        merge_kind = self._merge_kind(before_head, self.base_head)
        status: dict[str, object] = {
            "action": "pull",
            "remote": remote,
            "head": self.base_head,
            "merge_kind": merge_kind,
        }
        if merge_kind == "merge":
            status["fsck"] = self.fsck(
                self._pull_changed_paths(before_head, self.base_head)
            )
        return status

    def push_remote(self, remote: str) -> dict[str, str]:
        """Push the tracker branch to the given remote."""
        self._validate_remote(remote)
        # Fetch first so the version check sees the current remote state.
        try:
            run_git(["fetch", remote, TRACKER_BRANCH], cwd=self.repo)
        except subprocess.CalledProcessError:
            pass  # Remote branch may not exist yet; that's fine.
        if remote_branch_exists(self.repo, remote, TRACKER_BRANCH):
            self.check_versions_match(
                self.read_version(),
                self.read_remote_version(self.repo, remote),
                f"{remote}/{TRACKER_BRANCH}",
            )
        try:
            run_git(
                ["push", remote, f"{TRACKER_BRANCH}:{TRACKER_BRANCH}"], cwd=self.repo
            )
        except subprocess.CalledProcessError as exc:
            raise RemotePushPullError(
                f"push failed for {remote}/{TRACKER_BRANCH}: "
                f"{exc.stderr.strip() or exc.stdout.strip()}"
            ) from exc
        self.base_head = self.head()
        return {"action": "push", "remote": remote, "head": self.base_head}

    def autopush_enabled(self) -> bool:
        """Return True if gittoc.autopush is set to a truthy value in git config."""
        val = local_config_get(self.repo, "gittoc.autopush")
        return val.lower() in ("true", "1", "yes")

    def auto_pull(self) -> None:
        """Pull from the effective remote before a mutation.

        Skipped silently if no remote is configured or the remote branch does
        not exist yet.  Fetch/connection failures are logged and ignored so
        offline work is possible.  Raises SystemExit on merge conflict so the
        mutation is aborted before anything is written.
        """
        remote = self.effective_remote()
        if not remote:
            return
        if not remote_branch_exists(self.repo, remote, TRACKER_BRANCH):
            return
        try:
            status = self.pull_remote(remote)
        except RemotePushPullError as exc:
            print(
                f"warning: auto-pull fetch failed: {exc}; continuing with local state",
                file=sys.stderr,
            )
            return
        report = status.get("fsck")
        if isinstance(report, IntegrityReport) and not report.ok:
            raise SystemExit(
                "pull merged tracker changes but fsck found integrity issues:\n"
                f"{render_integrity_report(report)}"
            )

    def auto_push(self) -> None:
        """Push to the effective remote after a mutation.

        Network failures print a warning to stderr but do not abort — the local
        mutation has already been committed and is valid.
        """
        remote = self.effective_remote()
        if not remote:
            return
        try:
            self.push_remote(remote)
        except RemotePushPullError as exc:
            print(
                f"warning: auto-push failed: {exc}; run: gittoc push", file=sys.stderr
            )
        except SystemExit as exc:
            print(
                f"warning: auto-push failed: {exc}; run: gittoc push", file=sys.stderr
            )

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
            raise SystemExit(
                f"invalid state: {state} (valid: {', '.join(STATE_ORDER)})"
            )
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
        self._state_cache[issue.issue_id] = issue.state
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
        self._event_cache.pop(issue.issue_id, None)

    def event_entries(self, issue_id: str) -> list[dict]:
        """Return all event log entries for an issue, in chronological order.

        Note events are augmented with a computed ``note_id`` (1-based
        sequential index) so that individual notes are human-addressable.
        Results are cached for the lifetime of this Tracker instance.
        """
        if issue_id in self._event_cache:
            return self._event_cache[issue_id]
        path = self.find_event_path(issue_id)
        if not path or not path.exists():
            self._event_cache[issue_id] = []
            return []
        entries: list[dict] = []
        note_seq = 0
        with path.open("r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"warning: skipping malformed event at {path}:{lineno}",
                        file=sys.stderr,
                    )
                    continue
                if entry.get("kind") == "note":
                    note_seq += 1
                    entry["note_id"] = note_seq
                entries.append(entry)
        self._event_cache[issue_id] = entries
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
        """Run any pending tracker migrations sequentially.

        Each migration is guarded by a version check and commits its own
        VERSION bump.  Migrations must be idempotent — safe to re-run.

        NOTE for future format changes (v2+): when designing a new format
        version, consider adding or renaming a required field so that older
        parsers fail loudly on the new data rather than silently
        misinterpreting it.  This turns an unprotected old-client pull into
        a parse error instead of silent corruption.
        """
        fmt, layout = self.read_version()
        if fmt == 0 and layout == 0:
            self._write_version(CURRENT_FORMAT_VERSION, CURRENT_LAYOUT_VERSION)

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

    def _issue_state(self, issue_id: str) -> str:
        """Return the state of an issue, using cache when available."""
        if issue_id in self._state_cache:
            return self._state_cache[issue_id]
        path = self.find_issue_path(issue_id)
        state = path.parent.name
        self._state_cache[issue_id] = state
        return state

    def _build_state_cache(self) -> None:
        """Populate the state cache from all issue files on disk."""
        for state in STATE_ORDER:
            for path in self.state_dir(state).glob("T-*.json"):
                if not path.name.endswith(EVENT_SUFFIX):
                    self._state_cache[path.stem] = state

    def dependency_closed(self, issue_id: str) -> bool:
        """Return True if the named dependency issue is in a terminal state."""
        return self._issue_state(issue_id) in TERMINAL_STATES

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
            try:
                current_issue, _ = self.load_issue(current)
            except SystemExit:
                # Referenced dep does not exist; treat as a leaf node.
                print(
                    f"warning: dependency {current} not found, "
                    "skipping during cycle check",
                    file=sys.stderr,
                )
                continue
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
        """Return a dict of issue counts per state plus a 'ready' count.

        Counts for non-open states are computed by file glob to avoid parsing
        every issue JSON. Only open issues are fully loaded (for readiness).
        """
        counts = {state: 0 for state in STATE_ORDER}
        for state in STATE_ORDER:
            if state == "open":
                continue
            counts[state] = len(
                list(
                    p
                    for p in self.state_dir(state).glob("T-*.json")
                    if not p.name.endswith(EVENT_SUFFIX)
                )
            )
        self._build_state_cache()
        open_issues = self.list_issues(("open",))
        counts["open"] = len(open_issues)
        ready = sum(1 for issue in open_issues if self.ready(issue))
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
                raise SystemExit(
                    f"cannot claim non-ready issue: {issue.issue_id}"
                    f" (has unresolved dependencies)"
                )
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
                raise SystemExit(f"{dep_id} is not a dependency of {issue.issue_id}")
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

    def _relpath(self, path: Path) -> str:
        """Return a tracker-checkout-relative path string."""
        return str(path.relative_to(self.checkout))

    def _finding(
        self,
        message: str,
        *,
        path: Path | None = None,
        line: int | None = None,
        issue_ids: tuple[str, ...] = (),
        severity: str = "error",
    ) -> IntegrityFinding:
        """Build a normalized integrity finding."""
        return IntegrityFinding(
            severity=severity,
            message=message,
            path=self._relpath(path) if path is not None else None,
            line=line,
            issue_ids=issue_ids,
        )

    def _validate_event_file(self, path: Path) -> list[IntegrityFinding]:
        """Validate the JSONL structure of a single event file."""
        findings: list[IntegrityFinding] = []
        issue_ids = ()
        event_id = issue_id_from_path(path)
        if event_id is not None:
            issue_ids = (event_id,)
        try:
            with path.open("r", encoding="utf-8") as handle:
                for lineno, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError as exc:
                        findings.append(
                            self._finding(
                                f"malformed JSON: {exc}",
                                path=path,
                                line=lineno,
                                issue_ids=issue_ids,
                            )
                        )
                        continue
                    if not isinstance(entry, dict):
                        findings.append(
                            self._finding(
                                "event entry must be a JSON object",
                                path=path,
                                line=lineno,
                                issue_ids=issue_ids,
                            )
                        )
                        continue
                    for field in ("actor", "at", "kind", "text"):
                        if field not in entry:
                            findings.append(
                                self._finding(
                                    f"missing event field '{field}'",
                                    path=path,
                                    line=lineno,
                                    issue_ids=issue_ids,
                                )
                            )
                        elif not isinstance(entry[field], str):
                            findings.append(
                                self._finding(
                                    f"event field '{field}' must be a string",
                                    path=path,
                                    line=lineno,
                                    issue_ids=issue_ids,
                                )
                            )
        except OSError as exc:
            findings.append(self._finding(f"cannot read file: {exc}", path=path))
        return findings

    def _canonical_cycle(self, cycle: list[str]) -> tuple[str, ...]:
        """Rotate a dependency cycle so duplicate reports collapse to one key."""
        start = min(range(len(cycle)), key=lambda index: issue_number(cycle[index]))
        return tuple(cycle[start:] + cycle[:start])

    def fsck(self, paths: list[Path] | None = None) -> IntegrityReport:
        """Run a read-only integrity scan across tracker issues and event logs.

        When *paths* is ``None`` the full tracker is scanned.  When a list is
        given, only findings related to those paths (or the issue IDs they
        encode) are returned.  An empty list means nothing was changed, so the
        scan is skipped and an ok report is returned immediately.
        """
        if paths is not None and not paths:
            return IntegrityReport(
                findings=(), checked_paths=(), scanned_issues=0, scanned_event_logs=0
            )
        findings: list[IntegrityFinding] = []
        scope_paths = (
            {
                self._relpath(path.resolve())
                for path in paths
                if path.exists() and path.is_relative_to(self.checkout)
            }
            if paths is not None
            else None
        )
        checked_paths = tuple(sorted(scope_paths or ()))
        scope_issue_ids = (
            {
                issue_id
                for rel in scope_paths or set()
                for issue_id in [issue_id_from_path(Path(rel))]
                if issue_id is not None
            }
            if scope_paths is not None
            else set()
        )

        issue_files: list[Path] = []
        event_files: list[Path] = []
        issue_paths_by_file_id: dict[str, list[Path]] = {}
        event_paths_by_file_id: dict[str, list[Path]] = {}

        for state in STATE_ORDER:
            state_dir = self.state_dir(state)
            if not state_dir.exists():
                continue
            for entry in sorted(state_dir.iterdir(), key=lambda value: value.name):
                if entry.is_dir():
                    findings.append(
                        self._finding(
                            "unexpected directory in tracker state", path=entry
                        )
                    )
                    continue
                if entry.name.endswith(EVENT_SUFFIX):
                    event_id = issue_id_from_path(entry)
                    if event_id is None:
                        findings.append(
                            self._finding("unexpected event filename", path=entry)
                        )
                        continue
                    event_files.append(entry)
                    event_paths_by_file_id.setdefault(event_id, []).append(entry)
                    continue
                if entry.suffix == ".json":
                    issue_id = issue_id_from_path(entry)
                    if issue_id is None:
                        findings.append(
                            self._finding("unexpected issue filename", path=entry)
                        )
                        continue
                    issue_files.append(entry)
                    issue_paths_by_file_id.setdefault(issue_id, []).append(entry)
                    continue
                findings.append(
                    self._finding("unexpected file in tracker state", path=entry)
                )

        duplicate_file_ids = {
            issue_id
            for issue_id, paths_for_issue in issue_paths_by_file_id.items()
            if len(paths_for_issue) > 1
        }
        for issue_id, paths_for_issue in issue_paths_by_file_id.items():
            if len(paths_for_issue) <= 1:
                continue
            first = self._relpath(paths_for_issue[0])
            for path in paths_for_issue[1:]:
                findings.append(
                    self._finding(
                        f"duplicate issue file for {issue_id}; also present at {first}",
                        path=path,
                        issue_ids=(issue_id,),
                    )
                )

        for issue_id, paths_for_issue in event_paths_by_file_id.items():
            if len(paths_for_issue) <= 1:
                continue
            first = self._relpath(paths_for_issue[0])
            for path in paths_for_issue[1:]:
                findings.append(
                    self._finding(
                        f"duplicate event log for {issue_id}; also present at {first}",
                        path=path,
                        issue_ids=(issue_id,),
                    )
                )

        issues_by_file_id: dict[str, Issue] = {}
        issue_path_by_file_id: dict[str, Path] = {}
        issue_paths_by_logical_id: dict[str, list[Path]] = {}
        invalid_file_ids: set[str] = set()

        for path in issue_files:
            file_id = path.stem
            issue, errors = Issue.validate_path(path)
            if errors:
                invalid_file_ids.add(file_id)
                for error in errors:
                    findings.append(
                        self._finding(error, path=path, issue_ids=(file_id,))
                    )
                continue
            if file_id not in duplicate_file_ids:
                issues_by_file_id[file_id] = issue
                issue_path_by_file_id[file_id] = path
            if issue.issue_id != file_id:
                findings.append(
                    self._finding(
                        f"filename/id mismatch: file name encodes {file_id}, record id is {issue.issue_id}",
                        path=path,
                        issue_ids=(file_id, issue.issue_id),
                    )
                )
            issue_paths_by_logical_id.setdefault(issue.issue_id, []).append(path)

        for logical_id, paths_for_issue in issue_paths_by_logical_id.items():
            if len(paths_for_issue) <= 1:
                continue
            first = self._relpath(paths_for_issue[0])
            for path in paths_for_issue[1:]:
                findings.append(
                    self._finding(
                        f"duplicate issue record id {logical_id}; also present at {first}",
                        path=path,
                        issue_ids=(logical_id,),
                    )
                )

        for path in event_files:
            event_id = issue_id_from_path(path)
            if event_id is None:
                continue
            if event_id not in issue_paths_by_file_id:
                findings.append(
                    self._finding(
                        f"orphaned event log for missing issue {event_id}",
                        path=path,
                        issue_ids=(event_id,),
                    )
                )
            elif event_id in duplicate_file_ids:
                findings.append(
                    self._finding(
                        f"event log for {event_id} is ambiguous because the issue file exists in multiple states",
                        path=path,
                        issue_ids=(event_id,),
                    )
                )
            else:
                issue_path = issue_paths_by_file_id[event_id][0]
                if path.parent != issue_path.parent:
                    findings.append(
                        self._finding(
                            f"event log state mismatch for {event_id}; issue file is in {issue_path.parent.name}",
                            path=path,
                            issue_ids=(event_id,),
                        )
                    )
            findings.extend(self._validate_event_file(path))

        resolvable_ids = set(issues_by_file_id) - invalid_file_ids
        for issue_id, issue in issues_by_file_id.items():
            issue_path = issue_path_by_file_id[issue_id]
            for dep_id in issue.deps:
                if dep_id not in resolvable_ids:
                    findings.append(
                        self._finding(
                            f"dangling dependency on {dep_id}",
                            path=issue_path,
                            issue_ids=(issue_id, dep_id),
                        )
                    )

        seen_cycles: set[tuple[str, ...]] = set()
        visited: set[str] = set()
        stack: list[str] = []
        active: set[str] = set()

        def visit(issue_id: str) -> None:
            active.add(issue_id)
            stack.append(issue_id)
            issue = issues_by_file_id[issue_id]
            for dep_id in issue.deps:
                if dep_id not in resolvable_ids:
                    continue
                if dep_id in active:
                    cycle = stack[stack.index(dep_id) :]
                    key = self._canonical_cycle(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycle_path = " -> ".join(list(key) + [key[0]])
                        findings.append(
                            self._finding(
                                f"dependency cycle detected: {cycle_path}",
                                path=issue_path_by_file_id[key[0]],
                                issue_ids=key,
                            )
                        )
                    continue
                if dep_id not in visited:
                    visit(dep_id)
            stack.pop()
            active.remove(issue_id)
            visited.add(issue_id)

        for issue_id in sorted(resolvable_ids, key=issue_number):
            if issue_id not in visited:
                visit(issue_id)

        if scope_paths is not None:
            findings = [
                finding
                for finding in findings
                if finding.path in scope_paths
                or scope_issue_ids.intersection(finding.issue_ids)
            ]

        findings.sort(
            key=lambda finding: (
                finding.severity,
                finding.path or "",
                finding.line or 0,
                finding.message,
            )
        )
        return IntegrityReport(
            findings=tuple(findings),
            checked_paths=checked_paths,
            scanned_issues=len(issue_files),
            scanned_event_logs=len(event_files),
        )
