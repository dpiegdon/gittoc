"""Remote sync operations: pull, push, auto-push/pull, and remote configuration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from . import VERSION_FILE
from .common import (
    TRACKER_BRANCH,
    infer_remote,
    list_remotes,
    local_config_get,
    local_config_set,
    remote_branch_exists,
    run_git,
)
from .integrity import IntegrityReport, fsck, render_integrity_report

if TYPE_CHECKING:
    from .tracker import RemotePushPullError, Tracker


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


def autopush_enabled(tracker: "Tracker") -> bool:
    """Return True if gittoc.autopush is set to a truthy value in git config."""
    val = local_config_get(tracker.repo, "gittoc.autopush")
    return val.lower() in ("true", "1", "yes")


def configured_remote(tracker: "Tracker") -> str:
    """Return the explicitly configured tracker remote, or empty string."""
    return local_config_get(tracker.repo, "gittoc.remote")


def effective_remote(tracker: "Tracker") -> str:
    """Return the configured remote, falling back to the inferred one."""
    return configured_remote(tracker) or infer_remote(tracker.repo)


def remote_status(tracker: "Tracker") -> dict[str, object]:
    """Return a dict describing the current remote wiring state."""
    configured = configured_remote(tracker)
    inferred = infer_remote(tracker.repo)
    effective = configured or inferred
    branch_remote = local_config_get(tracker.repo, f"branch.{TRACKER_BRANCH}.remote")
    branch_merge = local_config_get(tracker.repo, f"branch.{TRACKER_BRANCH}.merge")
    return {
        "remotes": list_remotes(tracker.repo),
        "inferred_remote": inferred,
        "configured_remote": configured,
        "effective_remote": effective,
        "tracker_branch": TRACKER_BRANCH,
        "branch_config_remote": branch_remote,
        "branch_config_merge": branch_merge,
        "remote_branch_exists": bool(
            effective and remote_branch_exists(tracker.repo, effective, TRACKER_BRANCH)
        ),
    }


def configure_remote(tracker: "Tracker", remote: str) -> dict[str, object]:
    """Configure the tracker branch to use the given remote and return status."""
    if remote not in list_remotes(tracker.repo):
        raise SystemExit(f"unknown remote: {remote}")
    local_config_set(tracker.repo, "gittoc.remote", remote)
    local_config_set(tracker.repo, f"branch.{TRACKER_BRANCH}.remote", remote)
    local_config_set(
        tracker.repo,
        f"branch.{TRACKER_BRANCH}.merge",
        f"refs/heads/{TRACKER_BRANCH}",
    )
    return remote_status(tracker)


def _validate_remote(tracker: "Tracker", remote: str) -> None:
    if remote not in list_remotes(tracker.repo):
        raise SystemExit(f"unknown remote: {remote}")


def _merge_kind(tracker: "Tracker", before_head: str, after_head: str) -> str:
    if after_head == before_head:
        return "unchanged"
    proc = run_git(
        ["rev-list", "--parents", "-n", "1", after_head],
        cwd=tracker.checkout,
        check=False,
    )
    parent_count = max(len(proc.stdout.strip().split()) - 1, 0)
    return "merge" if parent_count > 1 else "fast-forward"


def _pull_changed_paths(
    tracker: "Tracker", before_head: str, after_head: str
) -> list[Path]:
    if not before_head or after_head == before_head:
        return []
    proc = run_git(
        ["diff", "--name-only", before_head, after_head, "--", "issues"],
        cwd=tracker.checkout,
        check=False,
    )
    return [
        tracker.checkout / line.strip()
        for line in proc.stdout.splitlines()
        if line.strip()
    ]


def pull_remote(tracker: "Tracker", remote: str) -> dict[str, object]:
    """Fetch and merge the tracker branch from the given remote."""
    from .tracker import RemotePushPullError

    _validate_remote(tracker, remote)
    before_head = tracker.head()
    try:
        run_git(["fetch", remote, TRACKER_BRANCH], cwd=tracker.repo)
    except subprocess.CalledProcessError as exc:
        raise RemotePushPullError(
            f"pull failed for {remote}/{TRACKER_BRANCH}: "
            f"{exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    if not remote_branch_exists(tracker.repo, remote, TRACKER_BRANCH):
        raise SystemExit(f"remote branch not found: {remote}/{TRACKER_BRANCH}")
    check_versions_match(
        tracker.read_version(),
        read_remote_version(tracker.repo, remote),
        f"{remote}/{TRACKER_BRANCH}",
    )
    proc = run_git(
        ["merge", "--no-edit", f"{remote}/{TRACKER_BRANCH}"],
        cwd=tracker.checkout,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"pull failed while merging {remote}/{TRACKER_BRANCH}; "
            f"resolve conflicts in {tracker.checkout} and re-run your command"
        )
    tracker.base_head = tracker.head()
    merge_kind = _merge_kind(tracker, before_head, tracker.base_head)
    status: dict[str, object] = {
        "action": "pull",
        "remote": remote,
        "head": tracker.base_head,
        "merge_kind": merge_kind,
    }
    if merge_kind == "merge":
        status["fsck"] = fsck(
            tracker, _pull_changed_paths(tracker, before_head, tracker.base_head)
        )
    return status


def push_remote(tracker: "Tracker", remote: str) -> dict[str, str]:
    """Push the tracker branch to the given remote."""
    from .tracker import RemotePushPullError

    _validate_remote(tracker, remote)
    try:
        run_git(["fetch", remote, TRACKER_BRANCH], cwd=tracker.repo)
    except subprocess.CalledProcessError:
        pass  # Remote branch may not exist yet; that's fine.
    if remote_branch_exists(tracker.repo, remote, TRACKER_BRANCH):
        check_versions_match(
            tracker.read_version(),
            read_remote_version(tracker.repo, remote),
            f"{remote}/{TRACKER_BRANCH}",
        )
    try:
        run_git(
            ["push", remote, f"{TRACKER_BRANCH}:{TRACKER_BRANCH}"], cwd=tracker.repo
        )
    except subprocess.CalledProcessError as exc:
        raise RemotePushPullError(
            f"push failed for {remote}/{TRACKER_BRANCH}: "
            f"{exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    tracker.base_head = tracker.head()
    return {"action": "push", "remote": remote, "head": tracker.base_head}


def auto_pull(tracker: "Tracker") -> None:
    """Pull from the effective remote before a mutation.

    Skipped silently if no remote is configured or the remote branch does
    not exist yet.  Fetch/connection failures are logged and ignored so
    offline work is possible.  Raises SystemExit on merge conflict so the
    mutation is aborted before anything is written.
    """
    from .tracker import RemotePushPullError

    remote = effective_remote(tracker)
    if not remote:
        return
    if not remote_branch_exists(tracker.repo, remote, TRACKER_BRANCH):
        return
    try:
        status = pull_remote(tracker, remote)
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


def auto_push(tracker: "Tracker") -> None:
    """Push to the effective remote after a mutation.

    Network failures print a warning to stderr but do not abort — the local
    mutation has already been committed and is valid.
    """
    from .tracker import RemotePushPullError

    remote = effective_remote(tracker)
    if not remote:
        return
    try:
        push_remote(tracker, remote)
    except RemotePushPullError as exc:
        print(f"warning: auto-push failed: {exc}; run: gittoc push", file=sys.stderr)
    except SystemExit as exc:
        print(f"warning: auto-push failed: {exc}; run: gittoc push", file=sys.stderr)
