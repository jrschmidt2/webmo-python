"""Tests for webmo.watchlist, in a temporary file.

    python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import watchlist  # noqa: E402

A = "https://a/rest.cgi"
B = "https://b/rest.cgi"


class WatchListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="webmo_watchlist_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "sub", "watched.json")

    def jobs(self, url=A, username="alice"):
        return [e["job"] for e in watchlist.entries(url, username, path=self.path)]

    def test_add_and_remove_by_server_and_user(self):
        self.assertEqual(self.jobs(), [])
        watchlist.add(A, "alice", [5, "6"], note="energy", path=self.path)
        watchlist.add(B, "alice", [5], path=self.path)
        watchlist.add(A, "bob", [7], path=self.path)
        self.assertEqual(self.jobs(), [5, 6])
        self.assertEqual(self.jobs(B), [5])
        self.assertEqual(self.jobs(A, "bob"), [7])
        entry = watchlist.entries(A, "alice", path=self.path)[0]
        self.assertEqual(entry["note"], "energy")
        self.assertRegex(entry["added"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertNotIn("pid", entry)
        watchlist.remove(A, "alice", [5, 99], path=self.path)
        self.assertEqual(self.jobs(), [6])
        self.assertEqual(self.jobs(B), [5])

    def test_update_keeps_note_and_sets_watcher(self):
        watchlist.add(A, "alice", [5], note="energy", path=self.path)
        watchlist.add(A, "alice", [5], pid=1234, watcher="my_watcher", path=self.path)
        entry = watchlist.entries(A, "alice", path=self.path)
        self.assertEqual(len(entry), 1)
        self.assertEqual((entry[0]["note"], entry[0]["pid"], entry[0]["watcher"]), ("energy", 1234, "my_watcher"))
        watchlist.add(A, "alice", [5], note="geometry", path=self.path)
        entry = watchlist.entries(A, "alice", path=self.path)[0]
        self.assertEqual(entry["note"], "geometry")
        self.assertNotIn("pid", entry)

    def test_reads_existing_skill_file(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            json.dump([{"url": A, "username": "alice", "job": 5, "added": "2026-11-01 10:00", "pid": 1, "note": "x"}], f)
        self.assertEqual(self.jobs(), [5])
        watchlist.add(A, "alice", [6], path=self.path)
        self.assertEqual(self.jobs(), [5, 6])

    def test_damaged_file_is_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.path))
        for text in ("not json", '{"a": 1}'):
            with open(self.path, "w") as f:
                f.write(text)
            self.assertEqual(self.jobs(), [])
        watchlist.add(A, "alice", [5], path=self.path)
        self.assertEqual(self.jobs(), [5])

    def test_default_path(self):
        with mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp}):
            self.assertEqual(watchlist.default_path(), os.path.join(self.tmp, ".webmo", "watched.json"))
            watchlist.add(A, "alice", [5])
            self.assertTrue(os.path.exists(os.path.join(self.tmp, ".webmo", "watched.json")))

    @unittest.skipIf(os.name == "nt", "uses a POSIX sleep process")
    def test_watcher_alive(self):
        self.assertFalse(watchlist.watcher_alive({"job": 5}))
        with subprocess.Popen(["sleep", "30"]) as proc:
            self.addCleanup(proc.kill)
            self.assertTrue(watchlist.watcher_alive({"pid": proc.pid, "watcher": "sleep"}))
            self.assertFalse(watchlist.watcher_alive({"pid": proc.pid, "watcher": "webmo_wait"}), "a reused pid")
            self.assertFalse(watchlist.watcher_alive({"pid": proc.pid}), "the default marker is webmo_wait")
            proc.kill()
            proc.wait()
            self.assertFalse(watchlist.watcher_alive({"pid": proc.pid, "watcher": "sleep"}))


if __name__ == "__main__":
    unittest.main()
