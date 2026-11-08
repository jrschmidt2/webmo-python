"""Tests for REST sessions: from_token, close(), the context manager, SessionExpiredError and the
request timeout. REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST, SessionExpiredError, MFARequiredError  # noqa: E402

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


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.get_response = FakeResponse(200, {"jobs": [1, 2]})
        self.login_response = FakeResponse(200, {"username": "alice", "token": "NEW"})
        for name in ("get", "post", "delete"):
            patcher = mock.patch("webmo.webmo_rest.requests." + name, side_effect=self.fake(name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake(self, method):
        def call(url, **kwargs):
            self.calls.append((method, url[len(BASE):], kwargs))
            if method == "post":
                return self.login_response
            if method == "delete":
                return FakeResponse(200, {})
            return self.get_response
        return call

    def logouts(self):
        return [c for c in self.calls if c[0] == "delete" and c[1] == "/sessions"]

    def test_from_token_never_logs_out(self):
        rest = WebMOREST.from_token(BASE, "alice", "OLD")
        self.assertEqual((rest.username, rest.token), ("alice", "OLD"))
        self.assertEqual(self.calls, [])  # no request until used
        self.assertEqual(rest.get_jobs(), [1, 2])
        self.assertEqual(self.calls[-1][2]["params"]["token"], "OLD")
        rest.close()
        with WebMOREST.from_token(BASE, "alice", "OLD"):
            pass
        rest2 = WebMOREST.from_token(BASE, "alice", "OLD")
        del rest2
        self.assertEqual(self.logouts(), [])

    def test_password_session_logs_out_once(self):
        rest = WebMOREST(BASE, "alice", "secret")
        self.assertEqual((rest.username, rest.token), ("alice", "NEW"))
        rest.close()
        rest.close()
        del rest
        self.assertEqual(len(self.logouts()), 1)
        self.assertEqual(self.logouts()[0][2]["params"]["token"], "NEW")

        with WebMOREST(BASE, "alice", "secret") as rest:
            rest.get_jobs()
        self.assertEqual(len(self.logouts()), 2)

        rest = WebMOREST(BASE, "alice", "secret")
        del rest  # still ends the session it created, as before
        self.assertEqual(len(self.logouts()), 3)

    def test_failed_logout_is_ignored(self):
        rest = WebMOREST(BASE, "alice", "secret")
        with mock.patch("webmo.webmo_rest.requests.delete", side_effect=requests.exceptions.ConnectionError()):
            rest.close()

    def test_session_expired(self):
        rest = WebMOREST.from_token(BASE, "alice", "OLD")
        self.get_response = FakeResponse(401, {"error": "Authentication failed"})
        with self.assertRaises(SessionExpiredError) as cm:
            rest.get_jobs()
        self.assertIsInstance(cm.exception, requests.exceptions.HTTPError)  # existing handlers still catch it
        self.assertEqual(cm.exception.response.status_code, 401)
        self.assertIn("Authentication failed", str(cm.exception))
        self.get_response = FakeResponse(403, {"error": "Not authorized for this resource"})
        with self.assertRaises(requests.exceptions.HTTPError) as cm:
            rest.get_jobs()
        self.assertNotIsInstance(cm.exception, SessionExpiredError)

    def test_failed_login_is_not_session_expired(self):
        self.login_response = FakeResponse(401, {"error": "Authentication failed"})
        with self.assertRaises(requests.exceptions.HTTPError) as cm:
            WebMOREST(BASE, "alice", "wrong")
        self.assertNotIsInstance(cm.exception, SessionExpiredError)

    def test_non_interactive_login(self):
        with mock.patch("getpass.getpass", side_effect=AssertionError("prompted")), \
                mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            with self.assertRaises(ValueError):
                WebMOREST(BASE, "alice", "", interactive=False)
            self.assertEqual(self.calls, [])

            self.login_response = FakeResponse(401, {"error": "MFA code required", "mfaRequired": True})
            with self.assertRaises(MFARequiredError) as cm:
                WebMOREST(BASE, "alice", "secret", interactive=False)
            self.assertIsInstance(cm.exception, requests.exceptions.HTTPError)
            self.assertEqual(cm.exception.response.status_code, 401)
            self.assertEqual(len(self.calls), 1)  # no second attempt

            #a wrong code, or a lockout, is an ordinary login error
            self.login_response = FakeResponse(401, {"error": "Invalid MFA code", "mfaRequired": True})
            with self.assertRaises(requests.exceptions.HTTPError) as cm:
                WebMOREST(BASE, "alice", "secret", totp="123456", interactive=False)
            self.assertNotIsInstance(cm.exception, (MFARequiredError, SessionExpiredError))

            self.login_response = FakeResponse(200, {"username": "alice", "token": "NEW"})
            rest = WebMOREST(BASE, "alice", "secret", totp="123456", interactive=False)
            self.assertEqual(self.calls[-1][2]["data"]["totp"], "123456")
            rest.close()

    def test_interactive_mfa_prompt(self):
        responses = [FakeResponse(401, {"error": "MFA code required", "mfaRequired": True}),
                     FakeResponse(200, {"username": "alice", "token": "NEW"})]
        with mock.patch("webmo.webmo_rest.requests.post", side_effect=lambda url, **kw: (self.calls.append(("post", "", kw)), responses.pop(0))[1]), \
                mock.patch("builtins.input", return_value="654321"):
            rest = WebMOREST(BASE, "alice", "secret")
        self.assertEqual(rest.token, "NEW")
        self.assertEqual(self.calls[-1][2]["data"]["totp"], "654321")
        rest.close()

    def test_timeout(self):
        rest = WebMOREST(BASE, "alice", "secret", timeout=(10, 300))
        self.assertEqual(self.calls[-1][2]["timeout"], (10, 300))  # the login
        rest.get_jobs()
        rest.get_job_info(1, 2)
        for method, path, kwargs in self.calls:
            self.assertEqual(kwargs.get("timeout"), (10, 300), path)
        rest.close()
        self.assertEqual(self.logouts()[-1][2]["timeout"], (10, 300))

        rest = WebMOREST.from_token(BASE, "alice", "OLD")
        rest.get_jobs()
        self.assertIsNone(self.calls[-1][2]["timeout"])  # the default: no timeout, as before
        rest = WebMOREST.from_token(BASE, "alice", "OLD", timeout=5)
        rest.get_jobs()
        self.assertEqual(self.calls[-1][2]["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
