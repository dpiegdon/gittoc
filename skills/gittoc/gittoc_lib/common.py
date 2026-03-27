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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_owner() -> str:
    for name in ("GITTOC_OWNER", "USER", "LOGNAME"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "unknown"


def run_git(
    args: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
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
    return Path(run_git(["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()


def validate_issue_id(issue_id: str) -> str:
    match = ISSUE_RE.match(issue_id)
    if not match:
        raise SystemExit(f"invalid issue id: {issue_id}")
    return issue_id


def issue_number(issue_id: str) -> int:
    return int(ISSUE_RE.match(validate_issue_id(issue_id)).group(1))


def validate_priority(priority: int) -> int:
    if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise SystemExit(
            f"invalid priority: {priority} (expected {PRIORITY_MIN}-{PRIORITY_MAX})"
        )
    return priority


def parse_state(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in STATE_SET:
        raise SystemExit(f"invalid state: {value}")
    return value


def branch_exists(root: Path, branch: str) -> bool:
    proc = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return proc.returncode == 0


def list_remotes(root: Path) -> list[str]:
    proc = run_git(["remote"], cwd=root, check=False)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def current_branch_upstream(root: Path) -> str:
    proc = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=root,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def infer_remote(root: Path) -> str:
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
    proc = run_git(["config", "--local", "--get", key], cwd=root, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def local_config_set(root: Path, key: str, value: str) -> None:
    run_git(["config", "--local", key, value], cwd=root)


def remote_branch_exists(root: Path, remote: str, branch: str) -> bool:
    proc = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"],
        cwd=root,
        check=False,
    )
    return proc.returncode == 0


def current_branch(root: Path) -> str:
    return run_git(["branch", "--show-current"], cwd=root).stdout.strip()


def worktree_path(root: Path) -> Path:
    return root / TRACKER_WORKTREE_PATH


def is_worktree(path: Path) -> bool:
    return path.exists() and (path / ".git").is_file()


def has_legacy_hidden_clone(path: Path) -> bool:
    return path.exists() and (path / ".git").is_dir()
