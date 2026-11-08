"""WebMO connection settings in a .env file, and connecting to WebMO with them.

The settings are KEY=VALUE lines (comments, blank lines, quotes and "export" are allowed):

    WEBMO_URL           the REST URL, ending in rest.cgi
    WEBMO_USERNAME      the WebMO username
    WEBMO_PASSWORD      the password, or
    WEBMO_PASSWORD_CMD  a shell command that prints it (e.g. from a keychain or password manager)
    WEBMO_TOKEN         a saved REST session token, tried before the password

Other keys are kept, and available with Config.get(). The file is looked for in this order:
$WEBMO_ENV_FILE; ./.env, if it sets WEBMO_URL; ~/.webmo/.env.

Example:
    from webmo import config
    rest = config.connect()                    # the saved token if valid, otherwise the password
    rest = config.login(totp="123456")         # a new session, whose token is saved in WEBMO_TOKEN
"""

import os
import subprocess

import requests

from .webmo_rest import WebMOREST, SessionExpiredError

KEYS = ("WEBMO_URL", "WEBMO_USERNAME", "WEBMO_PASSWORD", "WEBMO_PASSWORD_CMD", "WEBMO_TOKEN")
PASSWORD_CMD_TIMEOUT = 120


class ConfigError(RuntimeError):
    """A problem with the settings, with a reason for callers that word their own messages:

    'no_file' (no .env found), 'missing_key' (WEBMO_URL or WEBMO_USERNAME; see .key), 'no_credentials'
    (no password, password command or token), or 'password_command' (WEBMO_PASSWORD_CMD failed).
    .path is the .env file, if one was found.
    """

    def __init__(self, message, reason, path=None, key=None):
        super().__init__(message)
        self.reason = reason
        self.path = path
        self.key = key


def global_env_file():
    """~/.webmo/.env"""
    return os.path.join(os.path.expanduser("~"), ".webmo", ".env")


def find_env_file():
    """Returns the path of the .env file to use, or None if there is none."""
    override = os.environ.get("WEBMO_ENV_FILE")
    if override:
        return override if os.path.isfile(override) else None
    local = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(local) and "WEBMO_URL" in read_env(local):
        return local
    path = global_env_file()
    return path if os.path.isfile(path) else None


def read_env(path):
    """Returns the KEY=VALUE settings of a .env file as a dictionary."""
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            values[key] = value
    return values


def write_value(path, key, value):
    """Sets KEY=value in a .env file, keeping all other lines; the file is readable only by its owner."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        if "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            lines[i] = "%s=%s" % (key, value)
            break
    else:
        lines.append("%s=%s" % (key, value))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


class Config:
    """The settings of one .env file."""

    def __init__(self, values, path):
        self.values = dict(values)
        self.path = path

    def get(self, key, default=""):
        """Any setting, including keys this module doesn't use itself."""
        return self.values.get(key, default)

    @property
    def url(self):
        """WEBMO_URL, without a trailing slash."""
        return self.get("WEBMO_URL").rstrip("/")

    @property
    def username(self):
        return self.get("WEBMO_USERNAME")

    @property
    def token(self):
        return self.get("WEBMO_TOKEN")

    def has_password(self):
        """Whether WEBMO_PASSWORD or WEBMO_PASSWORD_CMD is set."""
        return bool(self.get("WEBMO_PASSWORD") or self.get("WEBMO_PASSWORD_CMD"))

    def get_password(self, interactive=False):
        """Returns WEBMO_PASSWORD, or the output of WEBMO_PASSWORD_CMD ('' if neither is set).

        The command's stderr is passed through, and its stdin too if interactive is True, so keychain
        or pinentry prompts still work. Raises ConfigError ('password_command') if it fails.
        """
        if self.get("WEBMO_PASSWORD") or not self.get("WEBMO_PASSWORD_CMD"):
            return self.get("WEBMO_PASSWORD")
        command = self.get("WEBMO_PASSWORD_CMD")
        try:
            result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True,
                                    timeout=PASSWORD_CMD_TIMEOUT, stdin=None if interactive else subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise ConfigError("WEBMO_PASSWORD_CMD did not finish within %d minutes: %s"
                              % (PASSWORD_CMD_TIMEOUT // 60, command), "password_command", self.path) from None
        if result.returncode != 0:
            raise ConfigError("WEBMO_PASSWORD_CMD failed (exit status %d): %s" % (result.returncode, command),
                              "password_command", self.path)
        password = result.stdout.rstrip("\r\n")
        if not password:
            raise ConfigError("WEBMO_PASSWORD_CMD printed nothing: %s" % command, "password_command", self.path)
        return password

    def save(self, key, value):
        """Sets a value, in this object and in its .env file."""
        write_value(self.path, key, value)
        self.values[key] = value


def load(path=None, require_credentials=True):
    """Returns the Config from path, or from the .env file found by find_env_file().

    Raises ConfigError if there is no file, WEBMO_URL or WEBMO_USERNAME is missing, or (with
    require_credentials) there is no password, password command or token.
    """
    path = path or find_env_file()
    if path is None or not os.path.isfile(path):
        raise ConfigError("No WebMO .env file found (looked for $WEBMO_ENV_FILE, ./.env and %s)" % global_env_file(),
                          "no_file", path)
    cfg = Config(read_env(path), path)
    for key in ("WEBMO_URL", "WEBMO_USERNAME"):
        if not cfg.get(key):
            raise ConfigError("%s is missing from %s" % (key, path), "missing_key", path, key)
    if require_credentials and not cfg.has_password() and not cfg.token:
        raise ConfigError("%s has no WEBMO_PASSWORD, WEBMO_PASSWORD_CMD or WEBMO_TOKEN" % path, "no_credentials", path)
    return cfg


def token_is_valid(cfg, timeout=30):
    """Whether the saved WEBMO_TOKEN is still accepted by the server (one request)."""
    if not cfg.token:
        return False
    r = requests.get(cfg.url + "/folders", params={"username": cfg.username, "token": cfg.token}, timeout=timeout)
    return r.status_code != 401


def connect(cfg=None, timeout=None, interactive=False, hours=24):
    """Returns a logged-in WebMOREST: from the saved token if it's still valid (the session is left
    open by close()), otherwise from a new password login (which close() ends).

    Arguments:
        cfg(Config, optional): The settings; default load()
        timeout(float or tuple, optional): The timeout of each REST request (see WebMOREST)
        interactive(bool, optional): Whether the login may prompt (for an MFA code, or a password command)
        hours(int, optional): The lifetime of a new password session

    Raises:
        ConfigError: The settings are incomplete, or the password command failed
        SessionExpiredError: The token is no longer valid, and there is no password to log in with
        MFARequiredError: The account needs an MFA code (log in with login(totp=...) instead)
        requests.HTTPError: The login failed (e.g. a wrong password, or a lockout)
    """
    cfg = cfg or load()
    if cfg.token:
        if token_is_valid(cfg, timeout=timeout or 30):
            return WebMOREST.from_token(cfg.url, cfg.username, cfg.token, timeout=timeout)
        if not cfg.has_password():
            raise SessionExpiredError("The saved WEBMO_TOKEN in %s was rejected or has expired, and no password "
                                      "is set" % cfg.path)
    password = cfg.get_password(interactive)
    if not password:
        raise ConfigError("%s has no WEBMO_PASSWORD, WEBMO_PASSWORD_CMD or WEBMO_TOKEN" % cfg.path,
                          "no_credentials", cfg.path)
    return WebMOREST(cfg.url, cfg.username, password, hours, timeout=timeout, interactive=interactive)


def login(cfg=None, password=None, totp="", recovery_code="", hours=24, save=True, timeout=None, interactive=False):
    """Logs in with the password (and an MFA code, if given), and optionally saves the new session's
    token as WEBMO_TOKEN, for connect() to use later.

    Arguments:
        cfg(Config, optional): The settings; default load(require_credentials=False)
        password(str, optional): The password; default WEBMO_PASSWORD or WEBMO_PASSWORD_CMD, or a
            prompt if interactive is True
        totp(str, optional): The current code from an authenticator app
        recovery_code(str, optional): A single-use MFA recovery code, instead of totp
        hours(int, optional): The requested session lifetime (the server may cap it)
        save(bool, optional): Save the token in the .env file; the returned object is then detached,
            so close() leaves the session open
        timeout(float or tuple, optional): The timeout of each REST request
        interactive(bool, optional): Whether to prompt for a missing password or MFA code

    Returns:
        The logged-in WebMOREST

    Raises:
        ConfigError: No password is available (and interactive is False), or the password command failed
        MFARequiredError: The account needs an MFA code, and none was given (interactive is False)
        requests.HTTPError: The login failed (e.g. a wrong password or MFA code, or a lockout)
    """
    cfg = cfg or load(require_credentials=False)
    if password is None:
        password = cfg.get_password(interactive)
    if not password and not interactive:
        raise ConfigError("No password: %s has no WEBMO_PASSWORD or WEBMO_PASSWORD_CMD" % cfg.path,
                          "no_credentials", cfg.path)
    rest = WebMOREST(cfg.url, cfg.username, password, hours, totp=totp, recovery_code=recovery_code,
                     timeout=timeout, interactive=interactive)
    if save:
        cfg.save("WEBMO_TOKEN", rest.detach())
    return rest
