"""Tests for wait_for_job, with a fake clock and mocked job information.

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST, SessionExpiredError  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(status):
    response = mock.Mock(status_code=status)
    cls = SessionExpiredError if status == 401 else requests.exceptions.HTTPError
    return cls("%d Error" % status, response=response)


class WaitTest(unittest.TestCase):
    def setUp(self):
        self.rest = WebMOREST.from_token("https://server/rest.cgi", "alice", "T")
        self.clock = FakeClock()
        patcher = mock.patch("webmo.webmo_rest.time", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.polls = []
        self.timeline = {}  # job -> list of (time from which, status or None for unreadable)
        self.errors = {}    # poll index -> exception to raise

    def fake_infos(self, job_numbers):
        index = len(self.polls)
        self.polls.append((self.clock.now, list(job_numbers)))
        if index in self.errors:
            raise self.errors[index]
        infos = []
        for n in job_numbers:
            status = [s for t, s in self.timeline[n] if t <= self.clock.now][-1]
            if status is None:
                infos.append({"jobNumber": n, "error": "Resource not found"})
            else:
                infos.append({"jobNumber": n, "properties": {"jobStatus": status, "jobName": "j%d" % n}})
        return infos

    def wait(self, *jobs, **kwargs):
        with mock.patch.object(WebMOREST, "_get_job_infos", side_effect=self.fake_infos):
            return self.rest.wait_for_job(*jobs, **kwargs)

    def test_schedule_and_one_request_per_poll(self):
        self.timeline = {1: [(0, "running"), (100, "complete")], 2: [(0, "queued"), (50, "running"), (2000, "failed")]}
        result = self.wait(1, 2)
        self.assertEqual(result, {1: "complete", 2: "failed"})
        self.assertEqual(list(result), [1, 2])  # in the order asked
        self.assertEqual(self.clock.sleeps[:12], [5] * 12)  # first minute: every 5 s
        self.assertEqual(self.clock.sleeps[12], 30)
        self.assertIn(60, self.clock.sleeps)
        self.assertIn(120, self.clock.sleeps)
        self.assertNotIn(300, self.clock.sleeps)  # finished before 76 minutes
        self.assertEqual(self.polls[0][1], [1, 2])
        self.assertTrue(all(jobs == [2] for t, jobs in self.polls if t > 120))  # finished jobs are not polled again

    def test_late_interval(self):
        self.timeline = {1: [(0, "running"), (6 * 3600, "complete")]}
        self.wait(1)
        self.assertEqual(self.clock.sleeps[-1], 300)

    def test_fixed_poll_frequency(self):
        self.timeline = {1: [(0, "running"), (95, "complete")]}
        self.assertEqual(self.wait(1, poll_frequency=20), {1: "complete"})
        self.assertEqual(self.clock.sleeps, [20] * 5)

    def test_timeout_returns_current_status(self):
        self.timeline = {1: [(0, "running"), (30, "complete")], 2: [(0, "running")]}
        result = self.wait(1, 2, timeout=100)
        self.assertEqual(result, {1: "complete", 2: "running"})
        self.assertEqual(self.clock.now, 100)  # a last check at the deadline
        self.assertTrue(all(s <= 30 for s in self.clock.sleeps))

    def test_deleted_job(self):
        self.timeline = {1: [(0, "running"), (12, None)], 2: [(0, "running"), (20, "complete")]}
        self.assertEqual(self.wait(1, 2), {1: None, 2: "complete"})

    def test_callback_on_changes(self):
        self.timeline = {1: [(0, "queued"), (10, "running"), (40, "complete")]}
        changes = []
        self.wait(1, callback=lambda n, info: changes.append((n, info["properties"]["jobStatus"])))
        self.assertEqual(changes, [(1, "queued"), (1, "running"), (1, "complete")])

    def test_network_and_server_errors_are_retried(self):
        self.timeline = {1: [(0, "running"), (200, "complete")]}
        self.errors = {1: requests.exceptions.ConnectionError(), 2: http_error(503), 3: requests.exceptions.Timeout()}
        self.assertEqual(self.wait(1), {1: "complete"})
        self.assertEqual(self.clock.sleeps[:4], [5, 10, 20, 40])  # longer after each failure
        self.assertEqual(self.clock.sleeps[4], 30)  # back to the schedule (75 s in) after a success

    def test_retry_interval_is_capped(self):
        self.timeline = {1: [(0, "running"), (5000, "complete")]}
        self.errors = {i: requests.exceptions.ConnectionError() for i in range(1, 12)}
        self.wait(1)
        self.assertEqual(max(self.clock.sleeps), 600)

    def test_session_expired_and_client_errors_raise(self):
        self.timeline = {1: [(0, "running")]}
        self.errors = {2: http_error(401)}
        with self.assertRaises(SessionExpiredError):
            self.wait(1)
        self.polls = []
        self.errors = {0: http_error(400)}
        with self.assertRaises(requests.exceptions.HTTPError):
            self.wait(1)

    def test_no_jobs(self):
        with self.assertRaises(ValueError):
            self.rest.wait_for_job()


if __name__ == "__main__":
    unittest.main()
