"""Tests for the Javascript built for display_job_property / render_job_property.

No WebMO server or browser is needed: REST responses are mocked.

    python -m unittest discover -s tests -v
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webmo import WebMOREST  # noqa: E402
from webmo import render  # noqa: E402

GEOMETRY = {"jobNumber": 42, "xyz": "O 0 0 0\nH 0 0.76 -0.47\nH 0 -0.76 -0.47", "connections": "", "charges": "",
            "zmatrix": ""}

RESULTS = {
    "symbols": ["O", "H", "H"],
    "geometry": [0, 0, 0, 0, 0.76, -0.47, 0, -0.76, -0.47],
    "properties": {
        "dipole_moment": [1.0, 2.0, 2.0],
        "partial_charges": {"mulliken": [-0.8, 0.4, 0.4]},
        "vibrations": {
            "frequencies": [1650.0, 3800.0, 3900.0],
            "intensities": {"IR": [70.0, 5.0, 45.0], "raman": [1.0, 2.0, 3.0], "VCD": [0.1, 0.2, 0.3]},
            "displacement": [[0.1] * 9, [0.2] * 9, [0.3] * 9],
        },
        "excited_states": {"transition_energies": [7.1, 8.2], "intensities": [0.05, 0.2], "units": "eV"},
        "nmr_shifts": {"isotropic": [320.0, 31.0, 31.5], "anisotropy": [40.0, 10.0, 11.0]},
    },
}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def fake_get(url, params=None, **kwargs):
    if url.endswith("/geometry"):
        return FakeResponse(GEOMETRY)
    if url.endswith("/results"):
        return FakeResponse(RESULTS)
    raise AssertionError("unexpected request: %s" % url)


class OfflineREST(WebMOREST):
    def __del__(self):
        pass  # there is no real session to log out of


def make_rest():
    rest = OfflineREST.__new__(OfflineREST)  # skip the login in __init__
    rest._base_url = "https://server/rest.cgi"
    rest._auth = {"username": "alice", "token": "T"}
    return rest


class PropertyJavascriptTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("webmo.webmo_rest.requests.get", side_effect=fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rest = make_rest()

    def js(self, prop, **kwargs):
        return self.rest._property_javascript(42, prop, **kwargs)

    def test_geometry(self):
        js = self.js("geometry", width=600, height=500, rotate=(10, 20, 30))
        self.assertTrue(js.startswith("_call_when_ready(function(){") and js.endswith("})"))
        for call in ("_set_moledit_size(600,500);", "_set_moledit_background(255,255,255);",
                     "_set_moledit_geometry(", "_rotate_moledit_view(10.000000,20.000000,30.000000);",
                     "_display_moledit_screenshot(0,false);"):
            self.assertIn(call, js)

    def test_callback_port_and_transparency(self):
        js = self.js("geometry", transparent_background=True, callback_port=51234)
        self.assertIn("_display_moledit_screenshot(51234,true);", js)

    def test_dipole_moment(self):
        self.assertIn("_set_moledit_dipole_moment('1.000000:2.000000:2.000000:3.000000');", self.js("dipole_moment"))

    def test_partial_charges(self):
        self.assertIn("_set_moledit_partial_charge('1,X,-0.800000:2,X,0.400000:3,X,0.400000');",
                      self.js("partial_charges"))

    def test_vibrational_mode(self):
        js = self.js("vibrational_mode", property_index=2)
        self.assertIn("_set_moledit_vibrational_mode('1,0.200000,0.200000,0.200000:", js)
        self.assertIn("', 2, 3800.000000, 1.000000);", js)

    def test_orbital_screenshot_comes_from_callback(self):
        js = self.js("mo", property_index=5, callback_port=7)
        self.assertIn("_set_moledit_wavefunction(42,'mo', 5, 7, false);", js)
        self.assertNotIn("_display_moledit_screenshot", js)

    def test_surfaces_use_index_zero(self):
        self.assertIn("_set_moledit_wavefunction(42,'esp', 0, 0, false);", self.js("esp", property_index=3))

    def test_ir_spectrum(self):
        js = self.js("ir_spectrum", x_range=(4000, 400))
        self.assertIn("_set_datagrapher_ir_spectrum('1,-,1650.000000,70.000000:", js)
        self.assertIn(", 40.000000);", js)  # default peak width
        self.assertIn("_set_x_range(4000.000000, 400.000000);", js)
        self.assertIn("_display_datagrapher_screenshot(0);", js)

    def test_raman_and_vcd_use_their_intensities(self):
        self.assertIn("1,-,1650.000000,1.000000", self.js("raman_spectrum"))
        self.assertIn("1,-,1650.000000,0.100000", self.js("vcd_spectrum"))

    def test_uvvis(self):
        js = self.js("uvvis_spectrum")
        self.assertIn("_set_datagrapher_uvvis_spectrum('1,-,7.100000,0.050000:2,-,8.200000,0.200000', 'eV', 20.000000);", js)

    def test_nmr(self):
        self.assertIn("_set_datagrapher_nmr_spectrum('1,O,320.000000", self.js("cnmr_spectrum"))
        js = self.js("hnmr_spectrum", tms_shift=32.0)
        self.assertIn("2,H,1.000000,10.000000", js)  # TMS shift applied to hydrogens only
        self.assertIn("'H', 0.001000, 1);", js)      # relative spectrum
        js = self.js("hnmr_spectrum", proton_coupling=7.0)
        self.assertIn("_set_datagrapher_h1nmr_spectrum(", js)

    def test_missing_data_is_a_clear_error(self):
        saved = RESULTS["properties"].pop("vibrations")
        try:
            with self.assertRaisesRegex(ValueError, r"Job 42 has no vibrational \(IR\) data for 'ir_spectrum'"):
                self.js("ir_spectrum")
        finally:
            RESULTS["properties"]["vibrations"] = saved

    def test_index_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "property_index 9 is out of range"):
            self.js("vibrational_mode", property_index=9)

    def test_invalid_arguments(self):
        with self.assertRaisesRegex(ValueError, "Invalid property_name"):
            self.js("nonsense")
        with self.assertRaisesRegex(ValueError, "Invalid property_index"):
            self.js("geometry", property_index=0)


class SetupAndGuardsTest(unittest.TestCase):
    def test_viewer_setup_html(self):
        html = make_rest()._viewer_setup_html({"url_html": "https://h/webmo", "url_cgi": "https://h/cgi-bin/webmo"})
        self.assertIn("<script src='https://h/webmo/javascript/moledit_js/moledit_js.nocache.js'></script>", html)
        self.assertIn("orbitalSrc='https://h/cgi-bin/webmo/get_orbital.cgi'", html)
        self.assertIn("function _call_when_ready(func)", html)

    def test_render_refuses_inside_event_loop(self):
        async def call():
            make_rest().render_job_property(42, "geometry")
        with self.assertRaisesRegex(RuntimeError, "display_job_property"):
            asyncio.run(call())

    def test_launch_error_messages(self):
        self.assertIn("playwright install chromium",
                      render._launch_error_message("Executable doesn't exist at /x/chrome"))
        message = render._launch_error_message(
            "chrome: error while loading shared libraries: libgbm.so.1: cannot open shared object file")
        self.assertIn("libgbm.so.1 is missing", message)

    def test_orbital_messages(self):
        url = "https://h/get_orbital.cgi?jobNumber=7&type=mo&index=3&a=1"
        self.assertIn("No mo data is available for job 7", render._orbital_message(url, 404))
        self.assertIn("refused", render._orbital_message(url, 403))


if __name__ == "__main__":
    unittest.main()
