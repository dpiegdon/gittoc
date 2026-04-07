#!/usr/bin/env python3
"""End-to-end tests for gittoc."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "gittoc"


def run(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def run_fail(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a command expected to fail, returning the completed process."""
    return subprocess.run(
        [str(CLI), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def current_branch(cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


class GittocTestBase(unittest.TestCase):
    """Shared setUp/tearDown for all gittoc E2E tests."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        (self.repo / "README.md").write_text("test repo\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=self.repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def init_with_remote(self) -> Path:
        """Initialize tracker with a bare remote and return the remote path."""
        remote_repo = Path(self.tempdir.name) / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        run(["init"], self.repo)
        return remote_repo


class TestInitAndRemote(GittocTestBase):
    def test_init_creates_tracker(self) -> None:
        init_out = run(["init"], self.repo)
        self.assertIn("initialized tracker branch", init_out)

    def test_init_auto_configures_remote(self) -> None:
        self.init_with_remote()
        remote_status = json.loads(run(["remote", "--format", "json"], self.repo))
        self.assertEqual(remote_status["configured_remote"], "origin")
        self.assertEqual(remote_status["effective_remote"], "origin")
        self.assertEqual(remote_status["branch_config_remote"], "origin")
        self.assertEqual(remote_status["branch_config_merge"], "refs/heads/gittoc")
        self.assertFalse(remote_status["remote_branch_exists"])


class TestCreateAndList(GittocTestBase):
    def test_create_issues(self) -> None:
        run(["init"], self.repo)
        issue1 = run(
            ["new", "High priority task", "-b", "finish core work", "-p", "1"],
            self.repo,
        )
        issue2 = run(
            ["new", "Lower priority task", "-b", "depends on first", "-p", "4"],
            self.repo,
        )
        self.assertEqual(issue1, "T-1")
        self.assertEqual(issue2, "T-2")

    def test_create_with_deps(self) -> None:
        run(["init"], self.repo)
        run(["new", "Blocker task", "-p", "1"], self.repo)
        issue2 = run(["new", "Dependent task", "-d", "T-1"], self.repo)
        self.assertEqual(issue2, "T-2")
        show = run(["show", "T-2"], self.repo)
        self.assertIn("T-1", show)
        # T-2 should NOT be ready (blocked by T-1)
        ready_out = run(["unblocked", "--format", "compact"], self.repo)
        self.assertNotIn("T-2", ready_out)

    def test_list_alias_and_compact(self) -> None:
        run(["init"], self.repo)
        run(["new", "High priority task", "-p", "1"], self.repo)
        alias_list = run(["l", "--format", "compact"], self.repo).splitlines()
        self.assertEqual(alias_list[0], "T-1 p1 open High priority task")

    def test_summary(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1"], self.repo)
        run(["new", "Task two", "-p", "4"], self.repo)
        self.assertEqual(
            run(["sum"], self.repo),
            "open=2 claimed=0 blocked=0 closed=0 rejected=0 ready=2",
        )

    def test_list_all_states(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1"], self.repo)
        run(["close", "T-1"], self.repo)
        all_list = run(["list", "--all", "--format", "compact"], self.repo)
        self.assertIn("T-1 p1 closed Task one", all_list)

    def test_verbose_list(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1", "-b", "finish core work"], self.repo)
        verbose = run(["list", "--format", "verbose"], self.repo)
        self.assertIn("body: finish core work", verbose)
        self.assertIn("deps: -", verbose)


class TestDependenciesAndReady(GittocTestBase):
    def test_dep_and_ready(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "High priority task", "-p", "1"], self.repo)
        issue2 = run(["new", "Lower priority task", "-p", "4"], self.repo)
        run(["dep", issue2, issue1], self.repo)

        listing = run(["list"], self.repo).splitlines()
        self.assertIn(f"> {issue1} p1 [open] High priority task", listing[0])
        self.assertIn(f"* {issue2} p4 [open] Lower priority task  deps=1", listing[1])

    def test_ready_after_close(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Blocker", "-p", "1"], self.repo)
        issue2 = run(["new", "Blocked", "-p", "2"], self.repo)
        run(["dep", issue2, issue1], self.repo)
        run(["close", issue1], self.repo)
        ready = run(["unblocked"], self.repo)
        self.assertIn(issue2, ready)

    def test_self_dependency_rejected(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Task"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue1, issue1], self.repo)

    def test_cycle_rejected(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "A"], self.repo)
        issue2 = run(["new", "B"], self.repo)
        run(["dep", issue2, issue1], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue1, issue2], self.repo)

    def test_cannot_claim_non_ready(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Blocker", "-p", "1"], self.repo)
        issue2 = run(["new", "Blocked", "-p", "2"], self.repo)
        run(["dep", issue2, issue1], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["claim", issue2, "--owner", "tester"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(
                ["update", issue2, "--state", "claimed", "--owner", "tester"], self.repo
            )

    def test_remove_dependency(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Blocker", "-p", "1"], self.repo)
        issue2 = run(["new", "Blocked", "-p", "2"], self.repo)
        run(["dep", issue2, issue1], self.repo)
        shown = json.loads(run(["show", issue2, "-f", "json"], self.repo))
        self.assertEqual(shown["deps"], [issue1])
        run(["dep", issue2, issue1, "--remove"], self.repo)
        shown = json.loads(run(["show", issue2, "-f", "json"], self.repo))
        self.assertNotIn("deps", shown)

    def test_remove_nonexistent_dep_fails(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "A"], self.repo)
        issue2 = run(["new", "B"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue1, issue2, "--remove"], self.repo)

    def test_cycle_check_with_missing_dep(self) -> None:
        """Cycle detection should not crash if a dep references a non-existent issue."""
        run(["init"], self.repo)
        issue1 = run(["new", "A"], self.repo)
        issue2 = run(["new", "B"], self.repo)
        run(["dep", issue2, issue1], self.repo)
        # Manually inject a non-existent dep into T-1's JSON
        gittoc_dir = self.repo / ".git" / "gittoc"
        t1_path = gittoc_dir / "issues" / "open" / "T-1.json"
        data = json.loads(t1_path.read_text())
        data["deps"] = ["T-999"]
        t1_path.write_text(json.dumps(data, indent=2))
        # Cycle check traverses T-2 -> T-1 deps -> T-999 (missing).
        # Should not crash; T-1 depends on T-2 would still be a cycle.
        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue1, issue2], self.repo)


class TestClaimWorkflow(GittocTestBase):
    def test_claim_and_show(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Task", "-p", "1"], self.repo)
        claimed_out = run(["claim", issue1, "--owner", "tester"], self.repo)
        self.assertIn(f"! {issue1} p1 [claimed] Task  owner=tester", claimed_out)

        claimed = json.loads(run(["show", issue1, "-f", "json"], self.repo))
        self.assertEqual(claimed["state"], "claimed")
        self.assertTrue(claimed["path"].startswith("issues/claimed/"))

    def test_cannot_claim_closed(self) -> None:
        run(["init"], self.repo)
        issue1 = run(["new", "Task", "-p", "1"], self.repo)
        run(["close", issue1], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["claim", issue1, "--owner", "tester"], self.repo)

    def test_claimed_alias(self) -> None:
        """The 'c' alias maps to the 'claimed' list filter."""
        run(["init"], self.repo)
        issue1 = run(["new", "Task", "-p", "1"], self.repo)
        run(["claim", issue1, "--owner", "tester"], self.repo)
        claimed_list = run(["c"], self.repo)
        self.assertIn(issue1, claimed_list)


class TestLabels(GittocTestBase):
    def test_add_and_remove_labels(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        run(["update", issue, "-l", "feature,ux"], self.repo)
        run(["update", issue, "-l", "bug"], self.repo)
        run(["update", issue, "-x", "ux"], self.repo)
        labeled = json.loads(run(["show", issue, "-f", "json"], self.repo))
        self.assertEqual(labeled["labels"], ["feature", "bug"])

    def test_replace_labels(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        run(["update", issue, "-l", "feature,ux"], self.repo)
        run(["update", issue, "-L", "task,docs"], self.repo)
        replaced = json.loads(run(["show", issue, "-f", "json"], self.repo))
        self.assertEqual(replaced["labels"], ["task", "docs"])

    def test_cannot_combine_replace_and_add(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["update", issue, "-L", "feature", "-l", "bug"], self.repo)


class TestNotesAndHistory(GittocTestBase):
    def test_notes_and_history(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task", "-p", "1"], self.repo)
        run(["claim", issue, "--owner", "tester"], self.repo)
        run(["note", issue, "First note", "--actor", "tester"], self.repo)
        run(["n", issue, "Alias note", "--actor", "tester"], self.repo)
        run(["note", issue, "Third note", "--actor", "tester"], self.repo)
        run(["note", issue, "Fourth note", "--actor", "tester"], self.repo)
        run(["note", issue, "Fifth note truncation", "--actor", "tester"], self.repo)

        history = run(["show", issue, "-a"], self.repo)
        self.assertIn("claimed tester: tester", history)
        self.assertIn("note#1 tester: First note", history)

    def test_note_ids_sequential(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        run(["note", issue, "Alpha", "--actor", "a"], self.repo)
        run(["note", issue, "Beta", "--actor", "b"], self.repo)
        run(["note", issue, "Gamma", "--actor", "c"], self.repo)
        history = run(["show", issue, "-n"], self.repo)
        self.assertIn("note#1 a: Alpha", history)
        self.assertIn("note#2 b: Beta", history)
        self.assertIn("note#3 c: Gamma", history)
        # JSON output should include note_id field
        shown = json.loads(run(["show", issue, "-n", "-f", "json"], self.repo))
        entries = shown["recent_notes"]
        self.assertEqual(entries[0]["note_id"], 1)
        self.assertEqual(entries[2]["note_id"], 3)

    def test_notes_only_with_limit(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        run(["note", issue, "Note A", "--actor", "tester"], self.repo)
        run(["note", issue, "Note B", "--actor", "tester"], self.repo)
        run(["note", issue, "Note C", "--actor", "tester"], self.repo)
        notes_only = run(["show", issue, "-n", "-l", "1"], self.repo)
        self.assertIn("Note C", notes_only)
        self.assertNotIn("Note A", notes_only)

    def test_show_truncates_notes(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        for i in range(5):
            run(["note", issue, f"Note {i}", "--actor", "tester"], self.repo)

        shown = json.loads(run(["show", issue, "-f", "json"], self.repo))
        self.assertEqual(shown["recent_notes_total"], 5)
        self.assertEqual(shown["recent_notes_shown"], 3)
        self.assertEqual(len(shown["recent_notes"]), 3)
        self.assertIn(f"show {issue} -n", shown["recent_notes_hint"])

    def test_show_text_format(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "My Task", "-p", "2", "-l", "bug"], self.repo)
        run(["note", issue, "A note", "--actor", "tester"], self.repo)
        text = run(["show", issue], self.repo)
        self.assertIn("T-1 p2 [open] My Task", text)
        self.assertIn("labels: bug", text)
        self.assertIn("tester: A note", text)


class TestShowAndResume(GittocTestBase):
    def test_show_alias(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        shown = json.loads(run(["s", "T-1", "-f", "json"], self.repo))
        self.assertEqual(shown["id"], "T-1")

    def test_resume_auto_select(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1"], self.repo)
        resume = json.loads(run(["resume", "--format", "json"], self.repo))
        self.assertEqual(resume["id"], "T-1")

    def test_resume_prefers_claimed(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1"], self.repo)
        run(["new", "Task two", "-p", "2"], self.repo)
        run(["claim", "T-2", "--owner", "tester"], self.repo)
        resume = run(["resume", "--owner", "tester"], self.repo)
        self.assertIn("T-2", resume)
        self.assertIn("selection=claimed-by-owner", resume)

    def test_resume_falls_back_to_ready(self) -> None:
        run(["init"], self.repo)
        run(["new", "Blocker", "-p", "1"], self.repo)
        issue2 = run(["new", "Depends", "-p", "2"], self.repo)
        run(["dep", issue2, "T-1"], self.repo)
        run(["close", "T-1"], self.repo)
        resume = json.loads(run(["resume", "--format", "json"], self.repo))
        self.assertEqual(resume["id"], issue2)
        self.assertEqual(resume["selection"], "highest-priority-ready")

    def test_resume_alias(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        resume = json.loads(run(["r", "T-1", "--format", "json"], self.repo))
        self.assertEqual(resume["id"], "T-1")

    def test_resume_notes_in_output(self) -> None:
        run(["init"], self.repo)
        issue = run(["new", "Task"], self.repo)
        for i in range(5):
            run(["note", issue, f"Note {i}"], self.repo)
        resume = json.loads(run(["resume", issue, "--format", "json"], self.repo))
        self.assertEqual(len(resume["recent_notes"]), 3)
        self.assertEqual(resume["recent_notes_total"], 5)


class TestUpdate(GittocTestBase):
    def test_update_title_and_priority(self) -> None:
        run(["init"], self.repo)
        run(["new", "Original", "-p", "3"], self.repo)
        run(["update", "T-1", "--title", "Updated", "--priority", "1"], self.repo)
        updated = json.loads(run(["show", "T-1", "-a", "-f", "json"], self.repo))
        self.assertEqual(updated["title"], "Updated")
        self.assertEqual(updated["priority"], 1)
        self.assertTrue(any(entry["kind"] == "updated" for entry in updated["history"]))

    def test_update_state_to_blocked(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task", "-p", "2"], self.repo)
        run(["update", "T-1", "--state", "blocked"], self.repo)
        summary = run(["summary"], self.repo)
        self.assertIn("blocked=1", summary)

    def test_update_alias(self) -> None:
        """The 'up' alias maps to the 'update' command."""
        run(["init"], self.repo)
        run(["new", "Original"], self.repo)
        run(["up", "T-1", "--title", "Aliased"], self.repo)
        updated = json.loads(run(["show", "T-1", "-f", "json"], self.repo))
        self.assertEqual(updated["title"], "Aliased")

    def test_update_no_fields_is_noop(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        result = run_fail(["update", "T-1"], self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no fields to update", result.stderr)


class TestCloseAndReject(GittocTestBase):
    def test_close(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        run(["close", "T-1"], self.repo)
        summary = run(["summary"], self.repo)
        self.assertIn("closed=1", summary)

    def test_reject(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        run(["reject", "T-1"], self.repo)
        summary = run(["summary"], self.repo)
        self.assertIn("rejected=1", summary)


class TestLog(GittocTestBase):
    def test_log_for_issue(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        run(["close", "T-1"], self.repo)
        history = run(["log", "T-1"], self.repo)
        self.assertRegex(history, r"Close issue T-1 \([^)]+\)")

    def test_tracker_log(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        run(["claim", "T-1", "--owner", "tester"], self.repo)
        tracker_log = run(["log"], self.repo)
        self.assertIn("Claim issue T-1 for tester (tester)", tracker_log)

    def test_note_appears_in_log(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        run(["note", "T-1", "context"], self.repo)
        tracker_log = run(["log"], self.repo)
        self.assertIn("Add note to T-1", tracker_log)


class TestWorktreeIntegrity(GittocTestBase):
    def test_worktree_clean_after_operations(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task one", "-p", "1"], self.repo)
        run(["new", "Task two", "-p", "2"], self.repo)
        run(["close", "T-1"], self.repo)
        run(["close", "T-2"], self.repo)

        tracker_status = subprocess.run(
            ["git", "-C", str(self.repo / ".git" / "gittoc"), "status", "--short"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(tracker_status, "")

    def test_worktree_listed(self) -> None:
        run(["init"], self.repo)
        worktree_entry = subprocess.run(
            ["git", "worktree", "list"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn(str(self.repo), worktree_entry)


class TestRemoteTracking(GittocTestBase):
    def test_init_tracks_remote_gittoc_branch(self) -> None:
        source = Path(self.tempdir.name) / "source"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=source,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=source,
            check=True,
            capture_output=True,
        )
        (source / "README.md").write_text("source repo\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=source, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=source,
            check=True,
            capture_output=True,
        )

        run(["init"], source)
        issue = run(["new", "Remote tracker issue"], source)
        self.assertEqual(issue, "T-1")

        remote_repo = Path(self.tempdir.name) / "remote-clone.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=source,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", current_branch(source)],
            cwd=source,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "gittoc"],
            cwd=source,
            check=True,
            capture_output=True,
        )

        clone = Path(self.tempdir.name) / "clone"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone)],
            check=True,
            capture_output=True,
        )

        summary = run(["summary"], clone)
        self.assertEqual(
            summary, "open=1 claimed=0 blocked=0 closed=0 rejected=0 ready=1"
        )

        issue_data = json.loads(run(["show", "T-1", "-f", "json"], clone))
        self.assertEqual(issue_data["title"], "Remote tracker issue")
        self.assertTrue(issue_data["path"].startswith("issues/open/"))


class TestPullAndPush(GittocTestBase):
    def test_pull_and_push_tracker_branch(self) -> None:
        remote_repo = Path(self.tempdir.name) / "sync.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )

        source = Path(self.tempdir.name) / "source-sync"
        shutil.copytree(self.repo, source)
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=source,
            check=True,
            capture_output=True,
        )
        run(["init"], source)
        subprocess.run(
            ["git", "push", "-u", "origin", current_branch(source)],
            cwd=source,
            check=True,
            capture_output=True,
        )
        push_out = json.loads(run(["push", "origin", "--format", "json"], source))
        self.assertEqual(push_out["action"], "push")
        self.assertEqual(push_out["remote"], "origin")

        clone = Path(self.tempdir.name) / "clone-sync"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone)],
            check=True,
            capture_output=True,
        )
        run(["summary"], clone)

        new_issue = run(["new", "Pulled tracker issue"], source)
        self.assertEqual(new_issue, "T-1")
        run(["push", "origin"], source)

        pull_out = json.loads(run(["pull", "origin", "--format", "json"], clone))
        self.assertEqual(pull_out["action"], "pull")
        self.assertEqual(pull_out["remote"], "origin")
        pulled = json.loads(run(["show", "T-1", "-f", "json"], clone))
        self.assertEqual(pulled["title"], "Pulled tracker issue")

    def test_pull_alias(self) -> None:
        remote_repo = Path(self.tempdir.name) / "alias.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        run(["init"], self.repo)
        run(["push", "origin"], self.repo)

        clone = Path(self.tempdir.name) / "alias-clone"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone)],
            check=True,
            capture_output=True,
        )

        pull_alias = json.loads(run(["pl", "origin", "--format", "json"], clone))
        self.assertEqual(pull_alias["action"], "pull")

    def test_push_alias(self) -> None:
        remote_repo = Path(self.tempdir.name) / "ps-alias.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        run(["init"], self.repo)
        push_alias = json.loads(run(["ps", "origin", "--format", "json"], self.repo))
        self.assertEqual(push_alias["action"], "push")


class TestFsck(GittocTestBase):
    def test_fsck_clean_tracker(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        self.assertIn("fsck ok", run(["fsck"], self.repo))

    def test_fsck_reports_malformed_issue_and_orphaned_event_log(self) -> None:
        run(["init"], self.repo)
        run(["new", "Task"], self.repo)
        gittoc_dir = self.repo / ".git" / "gittoc"
        issue_path = gittoc_dir / "issues" / "open" / "T-1.json"
        issue_path.write_text("{not json\n", encoding="utf-8")
        orphan_event = gittoc_dir / "issues" / "open" / "T-9.events.jsonl"
        orphan_event.write_text('{"actor":"a","at":"b","kind":"note","text":"c"}\n')

        result = run_fail(["fsck"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("issues/open/T-1.json", result.stdout)
        self.assertIn("malformed JSON", result.stdout)
        self.assertIn("issues/open/T-9.events.jsonl", result.stdout)
        self.assertIn("orphaned event log", result.stdout)

    def test_fsck_reports_dangling_dependencies_and_cycles(self) -> None:
        run(["init"], self.repo)
        run(["new", "A"], self.repo)
        run(["new", "B"], self.repo)
        gittoc_dir = self.repo / ".git" / "gittoc"
        t1_path = gittoc_dir / "issues" / "open" / "T-1.json"
        t2_path = gittoc_dir / "issues" / "open" / "T-2.json"

        t1_data = json.loads(t1_path.read_text(encoding="utf-8"))
        t2_data = json.loads(t2_path.read_text(encoding="utf-8"))
        t1_data["deps"] = ["T-2"]
        t2_data["deps"] = ["T-1", "T-99"]
        t1_path.write_text(json.dumps(t1_data, indent=2) + "\n", encoding="utf-8")
        t2_path.write_text(json.dumps(t2_data, indent=2) + "\n", encoding="utf-8")

        result = run_fail(["fsck"], self.repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("dangling dependency on T-99", result.stdout)
        self.assertIn("dependency cycle detected: T-1 -> T-2 -> T-1", result.stdout)

    def test_pull_runs_fsck_after_nontrivial_merge(self) -> None:
        remote_repo = Path(self.tempdir.name) / "fsck-pull.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        run(["init"], self.repo)
        run(["new", "Seed issue"], self.repo)
        subprocess.run(
            ["git", "push", "-u", "origin", current_branch(self.repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        run(["push", "origin"], self.repo)

        clone_a = Path(self.tempdir.name) / "clone-a"
        clone_b = Path(self.tempdir.name) / "clone-b"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone_a)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone_b)],
            check=True,
            capture_output=True,
        )
        run(["summary"], clone_a)
        run(["summary"], clone_b)

        remote_event = (
            clone_a / ".git" / "gittoc" / "issues" / "open" / "T-1.events.jsonl"
        )
        with remote_event.open("a", encoding="utf-8") as handle:
            handle.write("{broken json\n")
        subprocess.run(
            ["git", "-C", str(clone_a / ".git" / "gittoc"), "add", "issues"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(clone_a / ".git" / "gittoc"),
                "commit",
                "-m",
                "Corrupt tracker events",
            ],
            check=True,
            capture_output=True,
        )
        run(["push", "origin"], clone_a)

        run(["new", "Local issue"], clone_b)
        result = run_fail(["pull", "origin"], clone_b)
        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed JSON", result.stderr)
        self.assertIn("issues/open/T-1.events.jsonl", result.stderr)


class TestAutoPush(GittocTestBase):
    def test_autopush_syncs_new_ticket(self) -> None:
        remote_repo = self.init_with_remote()
        subprocess.run(
            ["git", "push", "-u", "origin", "gittoc"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "gittoc.autopush", "true"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

        clone = Path(self.tempdir.name) / "clone-autopush"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(clone)],
            check=True,
            capture_output=True,
        )
        run(["summary"], clone)  # triggers init of gittoc worktree

        run(["new", "Auto-pushed ticket"], self.repo)

        # clone should see the ticket after pulling
        run(["pull", "origin"], clone)
        summary = run(["summary"], clone)
        self.assertIn("open=1", summary)

    def test_autopush_push_failure_warns_not_aborts(self) -> None:
        run(["init"], self.repo)
        subprocess.run(
            ["git", "config", "gittoc.autopush", "true"],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )
        # autopush is enabled but no remote is configured — push skipped silently
        issue = run(["new", "Ticket without remote"], self.repo)
        self.assertEqual(issue, "T-1")


if __name__ == "__main__":
    unittest.main()
