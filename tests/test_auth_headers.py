"""Tests for header credentials (X-WebMO-Username / X-WebMO-Token), long-lived session labels and
the session expiration time. REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import sys
import time
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST  # noqa: E402

BASE = "https://server/rest.cgi"


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = str(data)
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError("%d Error" % self.status_code, response=self)


class AuthHeadersTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.server_has_headers = True  # a WebMO 27 server
        self.login_data = {"username": "alice", "token": "TOK", "expires": 2000000000}
        for name in ("get", "post", "delete"):
            patcher = mock.patch("webmo.webmo_rest.requests." + name, side_effect=self.fake(name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake(self, method):
        def call(url, **kwargs):
            path = url[len(BASE):]
            self.calls.append((method, path, kwargs))
            if method == "post" and path == "/sessions":
                return FakeResponse(200, self.login_data)
            if path == "/status":
                probed = (kwargs.get("headers") or {}).get("X-WebMO-Probe")
                return FakeResponse(200, {"authHeaders": True} if (probed and self.server_has_headers) else {})
            if method == "delete":
                return FakeResponse(200, {"results": "success"})
            return FakeResponse(200, {"jobs": [], "folders": [], "results": "success", "jobNumber": 7})
        return call

    def last(self, path, method=None):
        return [c for c in self.calls if c[1] == path and method in (None, c[0])][-1]

    def assertNoCredentialsInParams(self, kwargs):
        for key in ("params", "data"):
            self.assertNotIn("token", kwargs.get(key) or {})
            self.assertNotIn("username", kwargs.get(key) or {})

    # --- header mode on a server that supports it ---
    def test_headers_are_used_when_the_server_supports_them(self):
        rest = WebMOREST(BASE, "alice", "pw")
        rest.get_jobs()
        _, _, kwargs = self.last("/jobs")
        self.assertEqual(kwargs["headers"], {"X-WebMO-Username": "alice", "X-WebMO-Token": "TOK"})
        self.assertNoCredentialsInParams(kwargs)
        self.assertTrue(rest.auth_headers)
        # the probe is made once
        rest.get_folders()
        self.assertEqual(len([c for c in self.calls if c[1] == "/status"]), 1)

    def test_posts_carry_no_credentials_in_the_body(self):
        rest = WebMOREST(BASE, "alice", "pw")
        rest.submit_job("job", "input", "gaussian")
        _, _, kwargs = self.last("/jobs")
        self.assertNoCredentialsInParams(kwargs)
        self.assertEqual(kwargs["headers"]["X-WebMO-Token"], "TOK")

    def test_close_signs_out_with_headers(self):
        rest = WebMOREST(BASE, "alice", "pw")
        rest.get_jobs()
        rest.close()
        _, _, kwargs = self.last("/sessions")
        self.assertEqual(kwargs["headers"]["X-WebMO-Token"], "TOK")
        self.assertNoCredentialsInParams(kwargs)

    # --- older servers, and turning it off ---
    def test_older_servers_get_parameters(self):
        self.server_has_headers = False
        rest = WebMOREST(BASE, "alice", "pw")
        rest.get_jobs()
        _, _, kwargs = self.last("/jobs")
        self.assertEqual(kwargs["params"]["token"], "TOK")
        self.assertEqual(kwargs["headers"], {})
        self.assertFalse(rest.auth_headers)

    def test_auth_headers_false_makes_no_probe(self):
        rest = WebMOREST(BASE, "alice", "pw", auth_headers=False)
        rest.get_jobs()
        self.assertFalse([c for c in self.calls if c[1] == "/status"])
        self.assertEqual(self.last("/jobs")[2]["params"]["token"], "TOK")

    def test_a_failed_probe_falls_back_to_parameters(self):
        def broken_status(url, **kwargs):
            if url.endswith("/status"):
                raise requests.exceptions.ConnectionError("no route")
            return self.fake("get")(url, **kwargs)
        with mock.patch("webmo.webmo_rest.requests.get", side_effect=broken_status):
            rest = WebMOREST(BASE, "alice", "pw")
            rest.get_jobs()
        self.assertEqual(self.last("/jobs")[2]["params"]["token"], "TOK")

    def test_setting_auth_directly_still_works(self):
        rest = WebMOREST.__new__(WebMOREST)
        rest._base_url = BASE
        rest._auth = {"username": "bob", "token": "T2"}
        rest.get_jobs()
        params = self.last("/jobs")[2]["params"]
        self.assertEqual((params["username"], params["token"]), ("bob", "T2"))
        self.assertEqual(rest.username, "bob")

    # --- from_token ---
    def test_from_token_probes_on_first_use(self):
        rest = WebMOREST.from_token(BASE, "alice", "OLD")
        self.assertEqual(self.calls, [])
        rest.get_jobs()
        self.assertEqual([c[1] for c in self.calls], ["/status", "/jobs"])
        self.assertEqual(self.last("/jobs")[2]["headers"]["X-WebMO-Token"], "OLD")
        self.assertIsNone(rest.expires)
        self.assertEqual(WebMOREST.from_token(BASE, "alice", "OLD", expires=123).expires, 123)

    # --- long-lived sessions ---
    def test_label_and_expiration_are_sent(self):
        WebMOREST(BASE, "alice", "pw", expiration=2160, label="Claude", auth_headers=False)
        _, _, kwargs = self.last("/sessions", "post")
        self.assertEqual(kwargs["data"]["label"], "Claude")
        self.assertEqual(kwargs["data"]["expiration"], 2160)

    def test_no_label_is_sent_by_default(self):
        WebMOREST(BASE, "alice", "pw", auth_headers=False)
        _, _, kwargs = self.last("/sessions", "post")
        self.assertNotIn("label", kwargs["data"])
        self.assertEqual(kwargs["data"]["expiration"], 24)

    def test_expires_comes_from_the_server(self):
        rest = WebMOREST(BASE, "alice", "pw", auth_headers=False)
        self.assertEqual(rest.expires, 2000000000)

    def test_expires_is_estimated_on_older_servers(self):
        self.login_data = {"username": "alice", "token": "TOK"}
        rest = WebMOREST(BASE, "alice", "pw", expiration=10, auth_headers=False)
        self.assertAlmostEqual(rest.expires, time.time() + 10 * 3600, delta=60)


if __name__ == "__main__":
    unittest.main()
