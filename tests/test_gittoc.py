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


def current_branch(cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


class GittocE2ETest(unittest.TestCase):
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
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True
        )
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
        self.assertEqual(remote_status["branch_config_merge"], "refs/heads/gittoc")
        self.assertFalse(remote_status["remote_branch_exists"])

        issue1 = run(
            [
                "new",
                "High priority task",
                "--body",
                "finish core work",
                "--priority",
                "1",
            ],
            self.repo,
        )
        issue2 = run(
            [
                "new",
                "Lower priority task",
                "--body",
                "depends on first",
                "--priority",
                "4",
            ],
            self.repo,
        )
        self.assertEqual(issue1, "T-1")
        self.assertEqual(issue2, "T-2")

        alias_list = run(["l", "--format", "compact"], self.repo).splitlines()
        self.assertEqual(alias_list[0], f"{issue1} p1 open High priority task")
        self.assertEqual(
            run(["s"], self.repo),
            "open=2 claimed=0 blocked=0 closed=0 rejected=0 ready=2",
        )

        run(["dep", issue2, issue1], self.repo)

        listing = run(["list"], self.repo).splitlines()
        self.assertIn(f"> {issue1} p1 [open] High priority task", listing[0])
        self.assertIn(f"* {issue2} p4 [open] Lower priority task deps=1", listing[1])
        self.assertEqual(len(listing), 2)

        refresh = run(["refresh", "--format", "json"], self.repo)
        self.assertIn('"open": 2', refresh)

        resume_initial = json.loads(run(["resume", "--format", "json"], self.repo))
        self.assertEqual(resume_initial["id"], issue1)
        self.assertEqual(resume_initial["priority"], 1)

        selected = json.loads(
            run(
                [
                    "show",
                    issue1,
                    "--field",
                    "id",
                    "--field",
                    "title",
                    "--field",
                    "priority",
                ],
                self.repo,
            )
        )
        self.assertEqual(
            selected, {"id": issue1, "priority": 1, "title": "High priority task"}
        )

        compact = run(["list", "--format", "compact"], self.repo).splitlines()
        self.assertEqual(compact[0], f"{issue1} p1 open High priority task")

        verbose = run(["list", "--format", "verbose"], self.repo)
        self.assertIn("body: finish core work", verbose)
        self.assertIn("deps: -", verbose)

        claimed_out = run(["claim", issue1, "--owner", "tester"], self.repo)
        self.assertIn(
            f"! {issue1} p1 [claimed] High priority task owner=tester", claimed_out
        )

        claimed = json.loads(run(["show", issue1], self.repo))
        self.assertEqual(claimed["state"], "claimed")
        self.assertEqual(claimed["priority"], 1)
        self.assertTrue(claimed["path"].startswith("issues/claimed/"))

        run(
            ["note", issue1, "Need to inspect logs first", "--actor", "tester"],
            self.repo,
        )
        run(["n", issue1, "Alias note", "--actor", "tester"], self.repo)
        run(
            ["note", issue1, "Checked the failing endpoint", "--actor", "tester"],
            self.repo,
        )
        run(
            ["note", issue1, "Need to confirm the retry path", "--actor", "tester"],
            self.repo,
        )
        run(
            ["note", issue1, "Final note should force truncation", "--actor", "tester"],
            self.repo,
        )
        history = run(["history", issue1], self.repo)
        self.assertIn("claimed tester: tester", history)
        self.assertIn("note tester: Need to inspect logs first", history)
        tracker_log = run(["log"], self.repo)
        self.assertIn("Add note to T-1 (tester)", tracker_log)
        notes_only = run(["history", issue1, "--notes-only", "--limit", "1"], self.repo)
        self.assertIn("Final note should force truncation", notes_only)
        self.assertNotIn("claimed tester: tester", notes_only)

        shown = json.loads(run(["show", issue1], self.repo))
        self.assertEqual(shown["recent_notes_total"], 5)
        self.assertEqual(shown["recent_notes_shown"], 3)
        self.assertEqual(len(shown["recent_notes"]), 3)
        self.assertIn("history T-1 --notes-only", shown["recent_notes_hint"])
        self.assertEqual(
            shown["recent_notes"][-1]["text"], "Final note should force truncation"
        )

        resume_json = json.loads(run(["resume", issue1, "--format", "json"], self.repo))
        self.assertEqual(resume_json["id"], issue1)
        self.assertEqual(len(resume_json["recent_notes"]), 3)
        self.assertEqual(resume_json["recent_notes"][-1]["kind"], "note")
        self.assertEqual(resume_json["recent_notes_total"], 5)

        resume_alias = json.loads(run(["r", issue1, "--format", "json"], self.repo))
        self.assertEqual(resume_alias["id"], issue1)

        shown_alias = json.loads(run(["sh", issue1], self.repo))
        self.assertEqual(shown_alias["id"], issue1)

        resume_auto = run(["resume", "--owner", "tester"], self.repo)
        self.assertIn(f"{issue1} p1 [claimed] High priority task", resume_auto)
        self.assertIn("selection=claimed-by-owner", resume_auto)

        run(["close", issue1], self.repo)
        claimed_alias = run(["c", issue2, "--owner", "tester"], self.repo)
        self.assertIn(
            f"! {issue2} p4 [claimed] Lower priority task deps=1 owner=tester",
            claimed_alias,
        )
        run(["update", issue2, "--state", "open"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["claim", issue1, "--owner", "tester"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(
                ["update", issue1, "--state", "claimed", "--owner", "tester"], self.repo
            )
        ready = run(["ready"], self.repo)
        self.assertIn(issue2, ready)

        issue3 = run(["new", "Blocked follow-up"], self.repo)
        run(["dep", issue3, issue2], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["claim", issue3, "--owner", "tester"], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(
                ["update", issue3, "--state", "claimed", "--owner", "tester"], self.repo
            )

        resume_ready = json.loads(run(["resume", "--format", "json"], self.repo))
        self.assertEqual(resume_ready["id"], issue2)
        self.assertEqual(resume_ready["selection"], "highest-priority-ready")

        run(["update", issue2, "--priority", "2", "--state", "blocked"], self.repo)
        summary = run(["summary"], self.repo)
        self.assertEqual(
            summary, "open=1 claimed=0 blocked=1 closed=1 rejected=0 ready=0"
        )

        run(["update", issue2, "--state", "open"], self.repo)
        ready = run(["ready"], self.repo)
        self.assertIn(f"> {issue2} p2 [open] Lower priority task deps=1", ready)

        run(
            ["update", issue2, "--title", "Updated title", "--priority", "1"], self.repo
        )
        updated = json.loads(run(["show", issue2, "--history"], self.repo))
        self.assertEqual(updated["title"], "Updated title")
        self.assertEqual(updated["priority"], 1)
        self.assertTrue(any(entry["kind"] == "updated" for entry in updated["history"]))

        run(["update", issue2, "-l", "feature,ux"], self.repo)
        run(["update", issue2, "-l", "bug"], self.repo)
        run(["update", issue2, "-x", "ux"], self.repo)
        labeled = json.loads(run(["show", issue2], self.repo))
        self.assertEqual(labeled["labels"], ["feature", "bug"])
        run(["update", issue2, "-L", "task,docs"], self.repo)
        replaced = json.loads(run(["show", issue2], self.repo))
        self.assertEqual(replaced["labels"], ["task", "docs"])
        with self.assertRaises(subprocess.CalledProcessError):
            run(["update", issue2, "-L", "feature", "-l", "bug"], self.repo)

        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue2, issue2], self.repo)
        issue4 = run(["new", "Cycle partner"], self.repo)
        run(["dep", issue4, issue2], self.repo)
        with self.assertRaises(subprocess.CalledProcessError):
            run(["dep", issue2, issue4], self.repo)

        run(["close", issue2], self.repo)
        run(["close", issue3], self.repo)
        run(["close", issue4], self.repo)
        history = run(["log", issue2], self.repo)
        self.assertRegex(history, rf"Close issue {issue2} \([^)]+\)")
        tracker_log = run(["log"], self.repo)
        self.assertIn("Claim issue T-2 for tester (tester)", tracker_log)

        all_list = run(["list", "--all", "--format", "compact"], self.repo)
        self.assertIn(f"{issue1} p1 closed High priority task", all_list)
        self.assertIn(f"{issue2} p1 closed Updated title", all_list)

        tracker_status = subprocess.run(
            ["git", "-C", str(self.repo / ".git" / "gittoc"), "status", "--short"],
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

        issue_data = json.loads(run(["show", "T-1"], clone))
        self.assertEqual(issue_data["title"], "Remote tracker issue")
        self.assertTrue(issue_data["path"].startswith("issues/open/"))

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
        pulled = json.loads(run(["show", "T-1"], clone))
        self.assertEqual(pulled["title"], "Pulled tracker issue")

        pull_alias = json.loads(run(["pl", "origin", "--format", "json"], clone))
        self.assertEqual(pull_alias["action"], "pull")

        push_alias = json.loads(run(["ps", "origin", "--format", "json"], source))
        self.assertEqual(push_alias["action"], "push")


if __name__ == "__main__":
    unittest.main()
