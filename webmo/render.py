"""Headless rendering of WebMO job properties (molecules, orbitals, surfaces, spectra) to PNG.

This drives WebMO's own MolEdit and DataGrapher viewers in a headless Chromium browser, the same
viewers that display_job_property uses inside Jupyter. It is used by WebMOREST.render_job_property
and requires the optional Playwright dependency:

    pip install 'webmo[render]'
    python -m playwright install chromium
"""

import base64
import re
import time

INSTALL_HINT = "pip install 'webmo[render]' && python -m playwright install chromium"

#MolEdit draws with WebGL; headless Chromium needs software WebGL (SwiftShader) for that
_BROWSER_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]

#the viewer page is served by request interception, so this host is never contacted
_PAGE_URL = "http://webmo-render.invalid/"


class RenderError(RuntimeError):
    """Rendering an image failed, e.g. the job's orbital data is missing or the image timed out."""


class RenderSetupError(RenderError):
    """The headless browser or WebMO's viewers could not be started, so no image can be rendered."""


class HeadlessRenderer:
    """A headless browser page with WebMO's viewers loaded, reused across renders.

    Arguments:
        setup_html(str): HTML that loads the viewers, from WebMOREST._viewer_setup_html
        timeout(float, optional): Seconds to wait for the viewers to load
    """

    def __init__(self, setup_html, timeout=60):
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except ImportError:
            raise ImportError("Rendering images requires Playwright: %s" % INSTALL_HINT) from None
        self._playwright = None
        self._browser = None
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(args=_BROWSER_ARGS)
        except PlaywrightError as e:
            self.close()
            raise RenderSetupError(_launch_error_message(str(e))) from None

        self._console = []
        self._orbital_error = None
        page = self._page = self._browser.new_page()
        page.on("console", lambda message: self._console.append(message.text))
        page.on("pageerror", lambda error: self._console.append(str(error)))
        page.on("response", self._check_orbital_response)
        page.on("requestfailed", self._check_orbital_failure)
        page.route(_PAGE_URL, lambda route: route.fulfill(
            content_type="text/html",
            body="<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>%s</body></html>" % setup_html))
        try:
            page.goto(_PAGE_URL)
            page.wait_for_function("document.getElementById('moledit-panel').children.length > 0 && "
                                   "document.getElementById('datagrapher-panel').children.length > 0",
                                   timeout=timeout * 1000)
        except PlaywrightError:
            self.close()
            raise RenderSetupError("WebMO's viewers did not load within %g s. Browser messages: %s"
                              % (timeout, self._recent_console())) from None
        #receive screenshots here instead of over the Jupyter websocket
        page.evaluate("window._display_uri = function(uri) { _clear_lock(); window.__webmo_image = uri; }")

    def render(self, javascript, timeout=60):
        """Runs javascript (from WebMOREST._property_javascript) and returns the resulting PNG bytes."""
        from playwright.sync_api import Error as PlaywrightError

        page = self._page
        self._console.clear()
        self._orbital_error = None
        #a failed render leaves WebMO's render lock set, which would delay this one by up to 5 s
        page.evaluate("window.__webmo_image = null; _clear_lock()")
        page.evaluate(javascript)
        deadline = time.time() + timeout
        #poll in short steps so a failed orbital download is reported right away
        while True:
            try:
                page.wait_for_function("window.__webmo_image", timeout=250)
                break
            except PlaywrightError:
                if self._orbital_error:
                    raise RenderError(self._orbital_error) from None
                if time.time() > deadline:
                    raise RenderError("No image after %g s. Browser messages: %s"
                                      % (timeout, self._recent_console())) from None
        uri = page.evaluate("window.__webmo_image")
        return base64.b64decode(uri.split(",", 1)[1])

    def close(self):
        """Closes the browser. Safe to call more than once."""
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = self._playwright = None

    def _check_orbital_response(self, response):
        if "get_orbital.cgi" in response.url and response.status >= 400:
            self._orbital_error = _orbital_message(response.url, response.status)

    def _check_orbital_failure(self, request):
        #servers before WebMO 26 omit the CORS header on errors, so a missing file looks like a failed request
        if "get_orbital.cgi" in request.url:
            self._orbital_error = _orbital_message(request.url, None)

    def _recent_console(self):
        return "; ".join(self._console[-5:]) or "none"


def _orbital_message(url, status):
    job = re.search(r"jobNumber=(\d+)", url)
    kind = re.search(r"type=(\w+)", url)
    what = "%s data" % (kind.group(1) if kind else "orbital")
    job = "job %s" % job.group(1) if job else "this job"
    if status == 403:
        return "The WebMO server refused the %s request for %s (HTTP 403)." % (what, job)
    return ("No %s is available for %s; the calculation probably did not save orbitals or surfaces%s."
            % (what, job, "" if status else " (or the server could not be reached)"))


def _launch_error_message(error):
    if "Executable doesn't exist" in error:
        return "Chromium for Playwright is not installed. Run: python -m playwright install chromium"
    library = re.search(r"error while loading shared libraries: (\S+?):", error)
    if library:
        return ("Chromium cannot start because the system library %s is missing. Install the browser's "
                "system dependencies: on Debian/Ubuntu, 'python -m playwright install-deps chromium'; "
                "on RHEL/Rocky/Fedora, e.g. 'dnf install mesa-libgbm libdrm nss atk'." % library.group(1))
    return "Could not start headless Chromium: %s" % error.strip().splitlines()[0]
