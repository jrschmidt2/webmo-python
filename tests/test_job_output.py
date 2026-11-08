"""Tests for search_job_output and get_job_output_lines. REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST, UnsupportedServerError  # noqa: E402

RESULT = {"jobNumber": 5, "file": "output.log", "totalLines": 3, "truncated": False,
          "lines": [{"line": 2, "text": "SCF Done", "match": True}], "matches": 1, "totalMatches": 1}


class FakeResponse:
    def __init__(self, status, data, content_type="application/json"):
        self.status_code = status
        self._data = data
        self.text = str(data)
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError("%d Error" % self.status_code, response=self)


class OfflineREST(WebMOREST):
    def __del__(self):
        pass  # there is no real session to log out of


class JobOutputTest(unittest.TestCase):
    def setUp(self):
        self.rest = OfflineREST.__new__(OfflineREST)  # skip the login in __init__
        self.rest._base_url = "https://server/rest.cgi"
        self.rest._auth = {"username": "alice", "token": "T"}
        self.response = FakeResponse(200, RESULT)
        self.requests = []
        patcher = mock.patch("webmo.webmo_rest.requests.get", side_effect=self.fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_get(self, url, params=None, **kwargs):
        self.requests.append((url, params))
        return self.response

    def test_search_parameters(self):
        self.assertEqual(self.rest.search_job_output(5, "SCF Done"), RESULT)
        url, params = self.requests[-1]
        self.assertEqual(url, "https://server/rest.cgi/jobs/5/raw_output")
        self.assertEqual(params, {"search": ["SCF Done"], "username": "alice", "token": "T"})
        self.rest.search_job_output(5, ["SCF Done", "Normal termination"], ignore_case=True, context=0, max_matches=20)
        self.assertEqual(self.requests[-1][1], {"search": ["SCF Done", "Normal termination"], "ignoreCase": 1,
                                                "context": 0, "maxMatches": 20, "username": "alice", "token": "T"})
        self.assertEqual(self.rest._auth, {"username": "alice", "token": "T"})  # not modified

    def test_lines_parameters(self):
        self.rest.get_job_output_lines(5, tail=50)
        self.assertEqual(self.requests[-1][1]["tail"], 50)
        self.rest.get_job_output_lines(5, first=10, last=20)
        self.assertEqual(self.requests[-1][1]["lines"], "10-20")
        self.rest.get_job_output_lines(5, first=10)
        self.assertEqual(self.requests[-1][1]["lines"], "10-1009")
        for kwargs in ({}, {"first": 1, "tail": 5}):
            with self.assertRaises(ValueError):
                self.rest.get_job_output_lines(5, **kwargs)

    def test_old_server(self):
        self.response = FakeResponse(200, "the whole file", content_type="text/plain")
        with self.assertRaises(UnsupportedServerError):
            self.rest.search_job_output(5, "SCF Done")
        with self.assertRaises(UnsupportedServerError):
            self.rest.get_job_output_lines(5, tail=10)

    def test_errors(self):
        self.response = FakeResponse(400, {"error": "tail must be 1 to 1000"})
        with self.assertRaises(requests.exceptions.HTTPError) as cm:
            self.rest.get_job_output_lines(5, tail=5000)
        self.assertIn("tail must be 1 to 1000", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
