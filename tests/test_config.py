"""Tests for webmo.config: the .env file, connect() and login(). REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import config, WebMOREST, SessionExpiredError, MFARequiredError  # noqa: E402

URL = "https://server/cgi-bin/webmo/rest.cgi"


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


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="webmo_config_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(os.path.join(self.home, ".webmo"))
        os.makedirs(self.work)
        env = {"HOME": self.home, "USERPROFILE": self.home}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("WEBMO_ENV_FILE", None)
        cwd = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, cwd)

    def write(self, path, text):
        with open(path, "w") as f:
            f.write(text)
        return path

    def env(self, password="", token="", password_cmd="", extra=""):
        return self.write(os.path.join(self.tmp, "webmo.env"),
                          "# comment\nWEBMO_URL=%s/\nWEBMO_USERNAME=alice\nWEBMO_PASSWORD=%s\nWEBMO_PASSWORD_CMD=%s\n"
                          "WEBMO_TOKEN=%s\n%s" % (URL, password, password_cmd, token, extra))


class EnvFileTest(TempDirTest):
    def test_lookup_order(self):
        global_env = self.write(os.path.join(self.home, ".webmo", ".env"), "WEBMO_URL=g\n")
        self.assertEqual(config.find_env_file(), global_env)
        self.write(os.path.join(self.work, ".env"), "OTHER=1\n")  # a project .env for something else
        self.assertEqual(config.find_env_file(), global_env)
        local = self.write(os.path.join(self.work, ".env"), "WEBMO_URL=l\n")
        self.assertEqual(os.path.realpath(config.find_env_file()), os.path.realpath(local))
        override = self.write(os.path.join(self.tmp, "o.env"), "WEBMO_URL=o\n")
        with mock.patch.dict(os.environ, {"WEBMO_ENV_FILE": override}):
            self.assertEqual(config.find_env_file(), override)
        with mock.patch.dict(os.environ, {"WEBMO_ENV_FILE": os.path.join(self.tmp, "missing.env")}):
            self.assertIsNone(config.find_env_file())
        os.remove(local)
        os.remove(global_env)
        self.assertIsNone(config.find_env_file())

    def test_read_env_syntax(self):
        path = self.write(os.path.join(self.tmp, "x.env"),
                          "# comment\n\nA=1\nexport B = two \nC='quoted value'\nD=\"x=y\"\nnot a setting\nE=\n")
        self.assertEqual(config.read_env(path), {"A": "1", "B": "two", "C": "quoted value", "D": "x=y", "E": ""})

    def test_write_value_keeps_other_lines(self):
        path = self.write(os.path.join(self.tmp, "x.env"), "# keep me\nWEBMO_URL=u\nexport WEBMO_TOKEN=old\nZ=1\n")
        config.write_value(path, "WEBMO_TOKEN", "new")
        config.write_value(path, "NEW_KEY", "v")
        with open(path) as f:
            self.assertEqual(f.read(), "# keep me\nWEBMO_URL=u\nWEBMO_TOKEN=new\nZ=1\nNEW_KEY=v\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        created = os.path.join(self.tmp, "created.env")
        config.write_value(created, "A", "1")
        with open(created) as f:
            self.assertEqual(f.read(), "A=1\n")

    def test_load(self):
        cfg = config.load(self.env(password="pw", extra="WEBMO_MCP_OUTPUT=/out\n"))
        self.assertEqual((cfg.url, cfg.username, cfg.token), (URL, "alice", ""))
        self.assertEqual(cfg.get("WEBMO_MCP_OUTPUT"), "/out")
        self.assertEqual(cfg.get("NOT_SET", "default"), "default")
        self.assertTrue(cfg.has_password())

    def test_load_errors(self):
        with self.assertRaises(config.ConfigError) as cm:
            config.load()
        self.assertEqual(cm.exception.reason, "no_file")
        path = self.write(os.path.join(self.tmp, "x.env"), "WEBMO_URL=u\n")
        with self.assertRaises(config.ConfigError) as cm:
            config.load(path)
        self.assertEqual((cm.exception.reason, cm.exception.key, cm.exception.path), ("missing_key", "WEBMO_USERNAME", path))
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.env())
        self.assertEqual(cm.exception.reason, "no_credentials")
        self.assertEqual(config.load(self.env(), require_credentials=False).username, "alice")
        self.assertEqual(config.load(self.env(token="T")).token, "T")

    @unittest.skipIf(os.name == "nt", "uses POSIX shell commands")
    def test_password_command(self):
        self.assertEqual(config.load(self.env(password_cmd="echo s3cret")).get_password(), "s3cret")
        self.assertEqual(config.load(self.env(password="literal", password_cmd="echo other")).get_password(), "literal")
        for command, message in (("exit 3", "failed (exit status 3)"), ("true", "printed nothing")):
            with self.assertRaises(config.ConfigError) as cm:
                config.load(self.env(password_cmd=command)).get_password()
            self.assertEqual(cm.exception.reason, "password_command")
            self.assertIn(message, str(cm.exception))
        with mock.patch.object(config, "PASSWORD_CMD_TIMEOUT", 0.2):
            with self.assertRaises(config.ConfigError) as cm:
                config.load(self.env(password_cmd="sleep 5")).get_password()
        self.assertIn("did not finish", str(cm.exception))
        #without interactive, the command gets no stdin, so it can't wait for input
        self.assertEqual(config.load(self.env(password_cmd="cat; echo done")).get_password(), "done")


class ConnectTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.valid_tokens = {"GOOD"}
        self.login_response = FakeResponse(200, {"username": "alice", "token": "NEW"})
        for name in ("get", "post", "delete"):
            patcher = mock.patch("webmo.webmo_rest.requests." + name, side_effect=self.fake(name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake(self, method):
        def call(url, **kwargs):
            self.calls.append((method, url[len(URL):], kwargs))
            if method == "post":
                return self.login_response
            if method == "delete":
                return FakeResponse(200, {})
            ok = kwargs["params"].get("token") in self.valid_tokens
            return FakeResponse(200, {"folders": []}) if ok else FakeResponse(401, {"error": "Authentication failed"})
        return call

    def methods(self):
        return [(m, p) for m, p, _ in self.calls]

    def test_valid_token_is_used(self):
        rest = config.connect(config.load(self.env(password="pw", token="GOOD")))
        self.assertEqual(rest.token, "GOOD")
        self.assertEqual(self.methods(), [("get", "/folders")])
        rest.close()
        self.assertNotIn(("delete", "/sessions"), self.methods())  # the saved token stays valid

    def test_expired_token_falls_back_to_password(self):
        rest = config.connect(config.load(self.env(password="pw", token="STALE")), timeout=7)
        self.assertEqual(rest.token, "NEW")
        self.assertEqual(self.calls[-1][2]["timeout"], 7)
        rest.close()
        self.assertEqual(self.methods()[-1], ("delete", "/sessions"))  # its own session is ended

    def test_expired_token_without_password(self):
        with self.assertRaises(SessionExpiredError):
            config.connect(config.load(self.env(token="STALE")))

    def test_password_login(self):
        os.environ["WEBMO_ENV_FILE"] = self.env(password="pw")
        rest = config.connect()
        self.assertEqual(self.methods(), [("post", "/sessions")])
        self.assertEqual(self.calls[0][2]["data"]["password"], "pw")
        rest.close()

    def test_mfa_required(self):
        self.login_response = FakeResponse(401, {"error": "MFA code required", "mfaRequired": True})
        with mock.patch("builtins.input", side_effect=AssertionError("prompted")):
            with self.assertRaises(MFARequiredError):
                config.connect(config.load(self.env(password="pw")))

    def test_login_saves_token_and_keeps_session(self):
        path = self.env(password="pw", token="OLD")
        rest = config.login(config.load(path, require_credentials=False), totp="123456", hours=8)
        self.assertEqual(self.calls[-1][2]["data"]["totp"], "123456")
        self.assertEqual(self.calls[-1][2]["data"]["expiration"], 8)
        self.assertEqual(config.read_env(path)["WEBMO_TOKEN"], "NEW")
        rest.close()
        del rest
        self.assertNotIn(("delete", "/sessions"), self.methods())

    def test_login_without_saving(self):
        path = self.env(password="pw")
        rest = config.login(config.load(path), save=False)
        self.assertEqual(config.read_env(path)["WEBMO_TOKEN"], "")
        rest.close()
        self.assertEqual(self.methods()[-1], ("delete", "/sessions"))

    def test_login_password_argument_and_missing_password(self):
        path = self.env()
        config.login(config.load(path, require_credentials=False), password="typed")
        self.assertEqual(self.calls[-1][2]["data"]["password"], "typed")
        with self.assertRaises(config.ConfigError) as cm:
            config.login(config.load(path, require_credentials=False), password="")
        self.assertEqual(cm.exception.reason, "no_credentials")


class DetachTest(ConnectTest):
    def test_detach(self):
        rest = WebMOREST(URL, "alice", "pw")
        self.assertEqual(rest.detach(), "NEW")
        rest.close()
        del rest
        self.assertNotIn(("delete", "/sessions"), self.methods())


if __name__ == "__main__":
    unittest.main()
