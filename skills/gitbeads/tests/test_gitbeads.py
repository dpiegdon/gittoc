#!/usr/bin/env python3
"""End-to-end tests for gitbeads."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "gitbeads" / "gitbeads"


def run(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


class GitbeadsE2ETest(unittest.TestCase):
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

    def test_full_feature_set(self) -> None:
        remote_repo = Path(self.tempdir.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_repo)],
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

        init_out = run(["init"], self.repo)
        self.assertIn("initialized tracker branch", init_out)
        remote_status = json.loads(run(["remote", "--format", "json"], self.repo))
        self.assertEqual(remote_status["configured_remote"], "origin")
        self.assertEqual(remote_status["effective_remote"], "origin")
        self.assertEqual(remote_status["branch_config_remote"], "origin")
        self.assertEqual(remote_status["branch_config_merge"], "refs/heads/gitbeads")
        self.assertFalse(remote_status["remote_branch_exists"])

        issue1 = run(
            ["new", "High priority task", "--body", "finish core work", "--priority", "1"],
            self.repo,
        )
        issue2 = run(
            ["new", "Lower priority task", "--body", "depends on first", "--priority", "4"],
            self.repo,
        )
        self.assertEqual(issue1, "GB-1")
        self.assertEqual(issue2, "GB-2")

        run(["dep", issue2, issue1], self.repo)

        listing = run(["list"], self.repo).splitlines()
        self.assertIn(f"> {issue1} p1 [open] High priority task", listing[0])
        self.assertIn(f"* {issue2} p4 [open] Lower priority task deps=1", listing[1])
        self.assertEqual(len(listing), 2)

        refresh = run(["refresh", "--format", "json"], self.repo)
        self.assertIn('"open": 2', refresh)

        ready_one = json.loads(run(["ready-one", "--format", "json"], self.repo))
        self.assertEqual(ready_one["id"], issue1)
        self.assertEqual(ready_one["priority"], 1)

        selected = json.loads(
            run(["show", issue1, "--field", "id", "--field", "title", "--field", "priority"], self.repo)
        )
        self.assertEqual(selected, {"id": issue1, "priority": 1, "title": "High priority task"})

        compact = run(["list", "--format", "compact"], self.repo).splitlines()
        self.assertEqual(compact[0], f"{issue1} p1 open High priority task")

        verbose = run(["list", "--format", "verbose"], self.repo)
        self.assertIn("body: finish core work", verbose)
        self.assertIn("deps: -", verbose)

        next_out = run(["next", "--claim", "--owner", "tester"], self.repo)
        self.assertIn(f"! {issue1} p1 [claimed] High priority task owner=tester", next_out)

        claimed = json.loads(run(["show", issue1], self.repo))
        self.assertEqual(claimed["state"], "claimed")
        self.assertEqual(claimed["priority"], 1)
        self.assertTrue(claimed["path"].startswith("issues/claimed/"))

        run(["note", issue1, "Need to inspect logs first", "--actor", "tester"], self.repo)
        run(["note", issue1, "Checked the failing endpoint", "--actor", "tester"], self.repo)
        history = run(["history", issue1], self.repo)
        self.assertIn("claimed tester: tester", history)
        self.assertIn("note tester: Need to inspect logs first", history)
        notes_only = run(["history", issue1, "--notes-only", "--limit", "1"], self.repo)
        self.assertIn("Checked the failing endpoint", notes_only)
        self.assertNotIn("claimed tester: tester", notes_only)

        resume_json = json.loads(run(["resume", issue1, "--format", "json"], self.repo))
        self.assertEqual(resume_json["id"], issue1)
        self.assertEqual(len(resume_json["recent_notes"]), 2)
        self.assertEqual(resume_json["recent_notes"][-1]["kind"], "note")

        resume_auto = run(["resume", "--owner", "tester"], self.repo)
        self.assertIn(f"{issue1} p1 [claimed] High priority task", resume_auto)
        self.assertIn("selection=claimed-by-owner", resume_auto)

        run(["close", issue1], self.repo)
        ready = run(["ready"], self.repo)
        self.assertIn(issue2, ready)

        resume_ready = json.loads(run(["resume", "--format", "json"], self.repo))
        self.assertEqual(resume_ready["id"], issue2)
        self.assertEqual(resume_ready["selection"], "highest-priority-ready")

        run(["update", issue2, "--priority", "2", "--state", "blocked"], self.repo)
        summary = run(["summary"], self.repo)
        self.assertEqual(summary, "open=0 claimed=0 blocked=1 closed=1 ready=0")

        run(["update", issue2, "--state", "open"], self.repo)
        ready = run(["ready"], self.repo)
        self.assertIn(f"> {issue2} p2 [open] Lower priority task deps=1", ready)

        run(["update", issue2, "--title", "Updated title", "--priority", "1"], self.repo)
        updated = json.loads(run(["show", issue2, "--history"], self.repo))
        self.assertEqual(updated["title"], "Updated title")
        self.assertEqual(updated["priority"], 1)
        self.assertTrue(any(entry["kind"] == "updated" for entry in updated["history"]))

        run(["close", issue2], self.repo)
        history = run(["log", issue2], self.repo)
        self.assertIn(f"Close issue {issue2}", history)

        all_list = run(["list", "--all", "--format", "compact"], self.repo)
        self.assertIn(f"{issue1} p1 closed High priority task", all_list)
        self.assertIn(f"{issue2} p1 closed Updated title", all_list)

        tracker_status = subprocess.run(
            ["git", "-C", str(self.repo / ".git" / "gitbeads"), "status", "--short"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(tracker_status, "")

        remote_status = json.loads(run(["remote", "--format", "json"], self.repo))
        self.assertEqual(remote_status["configured_remote"], "origin")

        worktree_entry = subprocess.run(
            ["git", "worktree", "list"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn(str(self.repo), worktree_entry)


if __name__ == "__main__":
    unittest.main()
