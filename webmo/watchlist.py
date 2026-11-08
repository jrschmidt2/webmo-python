"""A persistent list of submitted WebMO jobs to report on later (~/.webmo/watched.json).

Programs that submit jobs add them here with a note on what to report, and remove them once they
have reported the result. A job can also be watched by a background process (pid), which removes
it when it exits; while that process is running, other programs leave the job to it. Entries are
keyed by server URL, username and job number, so one list serves several servers and accounts.

Each entry is a dictionary: url, username, job, added ("YYYY-MM-DD HH:MM"), and optionally note,
pid (the watching process) and watcher (a string in that process's command line, which guards
against a reused process ID; "webmo_wait" if not given).
"""

import json
import os
import subprocess
import time
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # Windows: no locking, which is fine for a single user
    fcntl = None

FINISHED = ("complete", "failed")
DEFAULT_WATCHER = "webmo_wait"


def default_path():
    """~/.webmo/watched.json"""
    return os.path.join(os.path.expanduser("~"), ".webmo", "watched.json")


@contextmanager
def _locked(path):
    """Yields the list of entries and writes it back atomically, under an exclusive lock."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".lock", "w") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        entries = _read(path)
        yield entries
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1)
        os.replace(tmp, path)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return []
    return entries if isinstance(entries, list) else []


def _matches(entry, url, username):
    return isinstance(entry, dict) and entry.get("url") == url and entry.get("username") == username


def entries(url, username, path=None):
    """Returns the entries for this server and user, in the order they were added."""
    return [e for e in _read(path or default_path()) if _matches(e, url, username)]


def add(url, username, jobs, note="", pid=None, watcher=None, path=None):
    """Adds jobs, or updates them if listed already: a new note replaces an earlier one (an empty
    note keeps it), and pid and watcher are set (or cleared, if pid is None).
    """
    with _locked(path or default_path()) as listed:
        for job in jobs:
            job = int(job)
            entry = next((e for e in listed if _matches(e, url, username) and e.get("job") == job), None)
            if entry is None:
                entry = {"url": url, "username": username, "job": job, "added": time.strftime("%Y-%m-%d %H:%M")}
                listed.append(entry)
            if note:
                entry["note"] = note
            entry.pop("pid", None)
            entry.pop("watcher", None)
            if pid:
                entry["pid"] = int(pid)
                if watcher:
                    entry["watcher"] = watcher


def remove(url, username, jobs, path=None):
    """Removes jobs from the list (jobs that aren't listed are ignored)."""
    jobs = set(int(job) for job in jobs)
    with _locked(path or default_path()) as listed:
        listed[:] = [e for e in listed if not (_matches(e, url, username) and e.get("job") in jobs)]


def watcher_alive(entry):
    """True if the entry's watching process (pid) is still running; False if it has none."""
    pid = entry.get("pid")
    if not pid:
        return False
    return _process_alive(int(pid), entry.get("watcher") or DEFAULT_WATCHER)


def _process_alive(pid, marker):
    """True if process pid is running and its command line contains marker."""
    if os.name == "nt":
        if not _windows_pid_alive(pid):  # os.kill(pid, 0) would send Ctrl-C there
            return False
        try:  # guard against PID reuse: Windows has neither /proc nor ps
            command = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % pid],
                capture_output=True, text=True, timeout=15).stdout
        except (OSError, subprocess.SubprocessError):
            return True
        return marker in command if command.strip() else True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    cmdline = "/proc/%d/cmdline" % pid
    if os.path.exists(cmdline):  # guard against PID reuse where /proc is available
        with open(cmdline, "rb") as f:
            return marker.encode() in f.read()
    try:  # macOS and other systems without /proc
        command = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return marker in command if command.strip() else True


def _windows_pid_alive(pid):
    """True if process pid exists and hasn't exited (Windows has no signal 0)."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: exists, but not ours
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
