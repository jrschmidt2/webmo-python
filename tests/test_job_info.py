"""Tests for get_job_info with one or several jobs. REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST  # noqa: E402

JOBS = {5: {"jobName": "water", "jobStatus": "complete"}, 6: {"jobName": "benzene", "jobStatus": "running"}}
FORBIDDEN = {"error": "Not authorized for this resource"}
NOT_FOUND = {"error": "Resource not found"}


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError("%d Error" % self.status_code, response=self)


class OfflineREST(WebMOREST):
    def __del__(self):
        pass  # there is no real session to log out of


class GetJobInfoTest(unittest.TestCase):
    def setUp(self):
        self.rest = OfflineREST.__new__(OfflineREST)  # skip the login in __init__
        self.rest._base_url = "https://server/rest.cgi"
        self.rest._auth = {"username": "alice", "token": "T"}
        self.multi = True  # whether the server has GET /jobs/info
        self.requests = []
        patcher = mock.patch("webmo.webmo_rest.requests.get", side_effect=self.fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def single(self, n):
        if n == 7:
            return 404, NOT_FOUND  # deleted
        if n not in JOBS:
            return 403, FORBIDDEN  # another user's
        return 200, {"jobNumber": n, "properties": JOBS[n]}

    def fake_get(self, url, params=None, **kwargs):
        path = url[len("https://server/rest.cgi"):]
        self.requests.append((path, (params or {}).get("jobNumber")))
        if path == "/jobs/info":
            if not self.multi:
                return FakeResponse(403, FORBIDDEN)  # older servers read 'info' as a job number
            entries = []
            for n in map(int, params["jobNumber"].split(",")):
                status, data = self.single(n)
                entries.append(data if status == 200 else {"jobNumber": n, "error": data["error"]})
            return FakeResponse(200, entries)
        if path.startswith("/jobs/"):
            return FakeResponse(*self.single(int(path.rsplit("/", 1)[1])))
        raise AssertionError("unexpected request: %s" % url)

    def test_single_job_is_unchanged(self):
        self.assertEqual(self.rest.get_job_info(5), {"jobNumber": 5, "properties": JOBS[5]})
        self.assertEqual(self.requests, [("/jobs/5", None)])
        with self.assertRaises(requests.exceptions.HTTPError):
            self.rest.get_job_info(7)

    def test_several_jobs_in_one_request(self):
        info = self.rest.get_job_info(6, 5, 99, 7)
        self.assertEqual(info, [{"jobNumber": 6, "properties": JOBS[6]}, {"jobNumber": 5, "properties": JOBS[5]},
                                {"jobNumber": 99, "error": "Not authorized for this resource"},
                                {"jobNumber": 7, "error": "Resource not found"}])
        self.assertEqual(self.requests, [("/jobs/info", "6,5,99,7")])

    def test_older_servers_are_asked_one_job_at_a_time(self):
        self.multi = False
        expected = [{"jobNumber": 6, "properties": JOBS[6]}, {"jobNumber": 99, "error": "Not authorized for this resource"},
                    {"jobNumber": 7, "error": "Resource not found"}]
        self.assertEqual(self.rest.get_job_info(6, 99, 7), expected)
        self.assertEqual([p for p, _ in self.requests], ["/jobs/info", "/jobs/6", "/jobs/99", "/jobs/7"])
        self.requests.clear()
        self.assertEqual(self.rest.get_job_info(6, 99, 7), expected)
        self.assertNotIn("/jobs/info", [p for p, _ in self.requests], "the fallback is remembered")

    def test_errors(self):
        with self.assertRaises(ValueError):
            self.rest.get_job_info()
        with mock.patch("webmo.webmo_rest.requests.get", return_value=FakeResponse(401, {"error": "Invalid"})):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.rest.get_job_info(5, 6)


if __name__ == "__main__":
    unittest.main()
