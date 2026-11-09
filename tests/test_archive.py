"""Tests for get_job_archive: the archive is binary. REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST  # noqa: E402

ARCHIVE = b"\x1f\x8b\x08\x00\xff\xfe\x80 not valid UTF-8"


class ArchiveTest(unittest.TestCase):
    def test_archive_is_returned_as_bytes(self):
        response = requests.Response()
        response.status_code = 200
        response._content = ARCHIVE
        response.headers["Content-Type"] = "application/x-compressed"
        rest = WebMOREST.from_token("https://server/rest.cgi", "alice", "T")
        with mock.patch("webmo.webmo_rest.requests.get", return_value=response) as get:
            self.assertEqual(rest.get_job_archive(5, 6), ARCHIVE)
        self.assertEqual(get.call_args.kwargs["params"]["jobNumber"], "5,6")


if __name__ == "__main__":
    unittest.main()
