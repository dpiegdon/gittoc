"""Git utility helpers and shared constants for gittoc."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TRACKER_BRANCH = "gittoc"
TRACKER_WORKTREE_PATH = Path(".git/gittoc")
ISSUES_ROOT = Path("issues")
STATE_ORDER = ("open", "claimed", "blocked", "closed", "rejected")
STATE_SET = set(STATE_ORDER)
TERMINAL_STATES = frozenset(("closed", "rejected"))
DEFAULT_PRIORITY = 3
PRIORITY_MIN = 1
PRIORITY_MAX = 5
ISSUE_RE = re.compile(r"^T-(\d+)$")
EVENT_SUFFIX = ".events.jsonl"


def now_utc() -> str:
    """Return the current UTC time as an ISO 8601 string with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_owner() -> str:
    """Resolve the current owner name from environment variables."""
    for name in ("GITTOC_OWNER", "USER", "LOGNAME"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "unknown"


def run_git(
    args: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a git subprocess and return the completed process."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, proc.args, output=proc.stdout, stderr=proc.stderr
        )
    return proc


def repo_root() -> Path:
    """Return the absolute path to the root of the current git repository."""
    return Path(run_git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()


def validate_issue_id(issue_id: str) -> str:
    """Raise SystemExit if issue_id does not match T-<n> format, otherwise return it."""
    match = ISSUE_RE.match(issue_id)
    if not match:
        raise SystemExit(
            f"invalid issue id: {issue_id} (expected T-<number>, e.g. T-42)"
        )
    return issue_id


def issue_number(issue_id: str) -> int:
    """Return the integer part of a T-<n> issue ID."""
    return int(ISSUE_RE.match(validate_issue_id(issue_id)).group(1))


def validate_priority(priority: int) -> int:
    """Raise SystemExit if priority is outside 1–5, otherwise return it."""
    if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise SystemExit(
            f"invalid priority: {priority} (expected {PRIORITY_MIN}-{PRIORITY_MAX})"
        )
    return priority


def parse_state(value: str | None) -> str | None:
    """Return state unchanged if valid, None if value is None; raise SystemExit if invalid."""
    if value is None:
        return None
    if value not in STATE_SET:
        raise SystemExit(f"invalid state: {value} (valid: {', '.join(STATE_ORDER)})")
    return value


def branch_exists(root: Path, branch: str) -> bool:
    """Return True if the named branch exists locally."""
    proc = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return proc.returncode == 0


def list_remotes(root: Path) -> list[str]:
    """Return the list of configured remote names."""
    proc = run_git(["remote"], cwd=root, check=False)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def current_branch_upstream(root: Path) -> str:
    """Return the upstream tracking ref for the current branch, or empty string."""
    proc = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def infer_remote(root: Path) -> str:
    """Infer the most likely remote name from upstream config or remote list."""
    upstream = current_branch_upstream(root)
    if "/" in upstream:
        return upstream.split("/", 1)[0]
    remotes = list_remotes(root)
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    return ""


def local_config_get(root: Path, key: str) -> str:
    """Read a local git config value, returning empty string if unset."""
    proc = run_git(["config", "--local", "--get", key], cwd=root, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def local_config_set(root: Path, key: str, value: str) -> None:
    """Write a local git config value."""
    run_git(["config", "--local", key, value], cwd=root)


def remote_branch_exists(root: Path, remote: str, branch: str) -> bool:
    """Return True if remote/branch exists as a remote-tracking ref."""
    proc = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
        cwd=root,
        check=False,
    )
    return proc.returncode == 0


def current_branch(root: Path) -> str:
    """Return the name of the currently checked-out branch."""
    return run_git(["branch", "--show-current"], cwd=root).stdout.strip()


def worktree_path(root: Path) -> Path:
    """Return the expected path of the hidden gittoc worktree."""
    return root / TRACKER_WORKTREE_PATH


def is_worktree(path: Path) -> bool:
    """Return True if path is an active git worktree (has a .git file, not dir)."""
    return path.exists() and (path / ".git").is_file()


def has_legacy_hidden_clone(path: Path) -> bool:
    """Return True if path looks like a legacy hidden clone (has a .git directory)."""
    return path.exists() and (path / ".git").is_dir()
