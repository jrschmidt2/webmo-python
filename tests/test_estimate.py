"""Tests for webmo.estimate, the port of WebMO's cpu_estimate.js.

    python -m unittest discover -s tests -v

The offline tests use copies of WebMO's JSON data in tests/fixtures. The parity test runs WebMO's
real cpu_estimate.js in headless Chromium and requires identical results over a large grid of
inputs; it needs Playwright with Chromium and the WebMO source tree (WEBMO_SOURCE_DIR, default
~/public_html/WebMO/source), and is skipped otherwise.
"""

import importlib.util
import itertools
import json
import math
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from webmo import estimate as est  # noqa: E402
from webmo import WebMOREST, UnsupportedServerError  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
WEBMO_SOURCE = os.environ.get("WEBMO_SOURCE_DIR",
                              os.path.join(os.path.expanduser("~"), "public_html", "WebMO", "source"))


def load_data(directory=FIXTURES):
    data = {}
    for key in ("method_scalings", "basis_counts", "atom_rows"):
        with open(os.path.join(directory, key + ".json")) as f:
            data[key] = json.load(f)
    return data


DATA = load_data()


def dropdown(options, default=None, aliases=None):
    variable = {"type": "dropdown", "options": {label: value for label, value in options},
                "default": default if default is not None else options[0][1]}
    if aliases is not None:
        variable["aliases"] = aliases
    return variable


CHECKBOX = {"type": "checkbox", "options": {"enabled": "on", "disabled": ""}, "default": ""}


class PortTest(unittest.TestCase):
    def test_parse_stoichiometry(self):
        self.assertEqual(est.parse_stoichiometry("C8H10N4O2"), {"C": 8, "H": 10, "N": 4, "O": 2})
        self.assertEqual(est.parse_stoichiometry("CH3CH2Cl"), {"C": 2, "H": 5, "Cl": 1})

    def test_basis_counts(self):
        self.assertEqual(est.get_basis_count(DATA, "H2O", "6-31G(d)"), 19)
        self.assertEqual(est.get_basis_count(DATA, "C8H10N4O2", "6-31G(d)"), 230)
        self.assertEqual(est.get_basis_count(DATA, "H2O", "6-31G**"), 25)
        self.assertEqual(est.get_basis_count(DATA, "H2O", "def2-SVP"), 24)
        self.assertEqual(est.get_basis_count(DATA, "H2O", "no-such-basis"), est.UNKNOWN)
        self.assertEqual(est.get_basis_count(DATA, "UF6", "6-31G(d)"), est.UNKNOWN)   # row > 4
        self.assertEqual(est.get_basis_count(DATA, "Xx2", "6-31G(d)"), est.UNKNOWN)   # not an element

    def test_job_types(self):
        args = (DATA, "gaussian", 1.0)
        energy = est.get_cpu_estimate(*args, "Molecular Energy", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)", False, False, 1)
        self.assertGreater(energy, 0)
        for template in ("Molecular Orbitals", "Natural Bond Orbitals", "Bond Orders"):
            self.assertEqual(est.get_cpu_estimate(*args, template, "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                                  False, False, 1), energy)
        self.assertAlmostEqual(est.get_cpu_estimate(*args, "Molecular Energy", "C8H10N4O2", "DFT-HYBRID",
                                                    "6-31G(d)", False, True, 1), 2 * energy)  # unrestricted
        self.assertAlmostEqual(est.get_cpu_estimate(*args, "Molecular Energy", "C8H10N4O2", "DFT-HYBRID",
                                                    "6-31G(d)", False, False, 16), energy / 16 ** 0.75)
        self.assertAlmostEqual(est.get_cpu_estimate(DATA, "gaussian", 2.5, "Molecular Energy", "C8H10N4O2",
                                                    "DFT-HYBRID", "6-31G(d)", False, False, 1), 2.5 * energy)
        opt = est.get_cpu_estimate(*args, "Geometry Optimization ", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                   False, False, 1)  # trailing space as in some template names
        self.assertGreater(opt, energy)
        both = est.get_cpu_estimate(*args, "Optimize + Vib Freq", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                    False, False, 1)
        freq = est.get_cpu_estimate(*args, "Vibrational Frequencies", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                    False, False, 1)
        self.assertAlmostEqual(both, opt + freq)
        self.assertEqual(est.get_cpu_estimate(*args, "Excited States and UV-VIS", "C8H10N4O2", "DFT-HYBRID",
                                              "6-31G(d)", False, False, 1), est.UNKNOWN)
        self.assertEqual(est.get_cpu_estimate(*args, "Coordinate Scan", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                              False, False, 1), est.UNKNOWN)
        scan = est.get_cpu_estimate(*args, "Coordinate Scan", "C8H10N4O2", "DFT-HYBRID", "6-31G(d)",
                                    False, False, 1, scan=(10, False))
        self.assertAlmostEqual(scan, energy + energy * 0.4 * 9)

    def test_unknown_combinations(self):
        self.assertEqual(est.get_cpu_estimate(DATA, "gaussian", 1.0, "Molecular Energy", "H2O", "MP2", "6-31G(d)",
                                              False, False, 1), est.UNKNOWN)
        self.assertEqual(est.get_cpu_estimate(DATA, "psi", 1.0, "NMR", "H2O", "HF", "6-31G(d)",
                                              False, False, 1), est.UNKNOWN)  # no GIAO factor for psi

    def test_format_time(self):
        self.assertEqual(est.format_time(59.9), "< 1 minute")
        self.assertEqual(est.format_time(60), "~1 minute(s)")
        self.assertEqual(est.format_time(600), "~7-13 minutes")
        self.assertEqual(est.format_time(1800), "~20-40 minutes")
        self.assertEqual(est.format_time(5400), "~1-3 hours")
        self.assertEqual(est.format_time(36000), "~7-13 hours")
        self.assertEqual(est.js_round(2.5), 3)  # javascript rounds halves up
        self.assertEqual(est.js_round(-0.5), 0)

    def test_direct_scf_rule(self):
        self.assertTrue(est.recommend_direct_scf(DATA, "orca", 301, 1, False))
        self.assertFalse(est.recommend_direct_scf(DATA, "orca", 300, 1, False))
        self.assertTrue(est.recommend_direct_scf(DATA, "orca", 10, 1, True))      # ORCA needs it with RI
        self.assertTrue(est.recommend_direct_scf(DATA, "gaussian", 10, 2, False))  # several cores
        self.assertFalse(est.recommend_direct_scf(DATA, "gaussian", 5000, 1, False))  # no threshold


class SettingsTest(unittest.TestCase):
    def test_stoichiometry_from_geometry(self):
        rows = DATA["atom_rows"]
        self.assertEqual(est.stoichiometry_from_geometry("O 0 0 0\nH 0 1 0\nH 0 -1 0\n", rows), "H2O")
        self.assertEqual(est.stoichiometry_from_geometry("O 8 0 0 0\nH 1 0 1 0\nH 1 0 -1 0", rows), "H2O")
        self.assertEqual(est.stoichiometry_from_geometry("6 0 0 0\n17 1 0 0\n1 0 1 0", rows), "CHCl")
        self.assertEqual(est.stoichiometry_from_geometry("C1 0 0 0\nX 0 0 1\nH2 1 0 0\ncl 0 1 0", rows), "CHCl")
        self.assertEqual(est.stoichiometry_from_geometry("", rows), "")

    def test_gaussian_theory_aliases_and_unrestricted(self):
        template = {"variables": {
            "theory": dropdown([("HF", "HF"), ("B3LYP", "B3LYP")], aliases={"B3LYP": "DFT-HYBRID"}),
            "method": {"type": "text", "default": ""},   # internal variable, not the method choice
            "basisSet": dropdown([("6-31G(d)", "6-31G(d)"), ("def2-SVP", "Def2SVP")], aliases={"Def2SVP": "def2-SVP"}),
            "unrestricted": dropdown([("Default", ""), ("Restricted", "R"), ("Unrestricted", "U")]),
            "multiplicity": {"type": "text", "default": "1"},
        }}
        self.assertEqual(est.job_settings("gaussian", template, {"theory": "B3LYP", "basisSet": "Def2SVP"}),
                         ("DFT-HYBRID", "def2-SVP", False))
        self.assertTrue(est.job_settings("gaussian", template, {"multiplicity": 2})[2])
        self.assertFalse(est.job_settings("gaussian", template, {"multiplicity": 2, "unrestricted": "R"})[2])
        self.assertEqual(est.job_settings("gaussian", template, {})[0], "HF")

    def test_functional_only_when_enabled(self):
        gamess = {"variables": {
            "theory": dropdown([("RHF", "SCFTYP=RHF"), ("DFT", "SCFTYP= RHF"), ("UHF", "SCFTYP=UHF")],
                               aliases={"SCFTYP=RHF": "HF", "SCFTYP=UHF": "HF"}),
            "functional": dropdown([("B3LYP", "B3LYP")], aliases={"B3LYP": "DFT-HYBRID"}),
            "basisSet": dropdown([("6-31G(d)", "N31 NGAUSS=6 NDFUNC=1")],
                                 aliases={"N31 NGAUSS=6 NDFUNC=1": "6-31G(d)"}),
        }}
        self.assertEqual(est.job_settings("gamess", gamess, {})[:3], ("HF", "6-31G(d)", False))
        self.assertEqual(est.job_settings("gamess", gamess, {"theory": "SCFTYP= RHF"})[0], "DFT-HYBRID")
        self.assertTrue(est.job_settings("gamess", gamess, {"theory": "SCFTYP=UHF"})[2])
        nwchem = {"variables": {
            "theory": dropdown([("HF", "scf"), ("DFT", "dft")], aliases={"scf": "HF"}),
            "functional": dropdown([("B3LYP", "b3lyp")], aliases={"b3lyp": "DFT-HYBRID"}),
            "basisSet": dropdown([("6-31G*", "6-31G*")]),
            "unrestricted": CHECKBOX,
        }}
        self.assertEqual(est.job_settings("nwchem", nwchem, {"theory": "dft"})[0], "DFT-HYBRID")
        self.assertTrue(est.job_settings("nwchem", nwchem, {"unrestricted": "on"})[2])
        psi = {"variables": {"method": dropdown([("Hartree-Fock", "scf")], aliases={"scf": "HF"}),
                             "basisSet": dropdown([("cc-pVDZ", "cc-pvdz")]),
                             "reference": dropdown([("RHF", "rhf"), ("UHF", "uhf")])}}
        self.assertEqual(est.job_settings("psi", psi, {"reference": "uhf"})[:3], ("HF", "cc-pvdz", True))

    def test_semiempirical_and_values_without_aliases(self):
        self.assertEqual(est.job_settings("xtb", {"variables": {}}, {})[:2], ("SEMIEMPIRICAL", "STO-3G"))
        # a value with no alias is used as it is
        template = {"variables": {"theory": dropdown([("B3LYP", "B3LYP")]),
                                  "basisSet": dropdown([("6-31G(d)", "6-31G(d)")])}}
        self.assertEqual(est.job_settings("gaussian", template, {})[:2], ("B3LYP", "6-31G(d)"))


def engines(scale=None, queue="compute"):
    host = {"ppnMin": "1", "ppnMax": "8"}
    if scale is not None:
        host["cpuEstScale"] = scale
    return {"orca": {"queues": {queue: host}}}


ORCA_TEMPLATE = {"id": "orca/global/4", "name": "Optimize + Vib Freq", "variables": {
    "method": dropdown([("HF", "HF"), ("B3LYP", "B3LYP")], aliases={"B3LYP": "DFT-HYBRID"}),
    "basisSet": dropdown([("def2-TZVP", "def2-TZVP")]),
    "densityFitting": CHECKBOX, "directSCF": dict(CHECKBOX, default="on"), "unrestricted": CHECKBOX,
}}
CAFFEINE = "\n".join("%s 0 0 %d" % (s, i) for i, s in enumerate("CCNCNCNCNCCOCO" + "H" * 10))


class EstimateTest(unittest.TestCase):
    """estimate(): the pure function, from data already fetched."""

    def test_recommendations(self):
        result = est.estimate(DATA, engines(1), ORCA_TEMPLATE, {"geometry": CAFFEINE, "method": "B3LYP"}, cores=8)
        self.assertEqual(result["stoichiometry"], "C8H10N4O2")
        self.assertEqual(result["recommend"], {"densityFitting": "on", "directSCF": "on"})
        self.assertTrue(result["density_fitting"])
        self.assertLess(result["density_fitting_seconds"]["on"], result["density_fitting_seconds"]["off"])
        self.assertAlmostEqual(result["seconds"], result["density_fitting_seconds"]["on"])

    def test_user_choices_are_kept(self):
        result = est.estimate(DATA, engines(1), ORCA_TEMPLATE,
                              {"geometry": CAFFEINE, "method": "B3LYP", "densityFitting": "", "directSCF": ""},
                              cores=8)
        self.assertEqual(result["recommend"], {})
        self.assertFalse(result["density_fitting"])

    def test_engine_and_job_type_come_from_the_template(self):
        upper = dict(ORCA_TEMPLATE, id="ORCA/user/1")
        self.assertEqual(est.estimate(DATA, engines(1), upper, {"geometry": CAFFEINE})["seconds"],
                         est.estimate(DATA, engines(1), ORCA_TEMPLATE, {"geometry": CAFFEINE})["seconds"])
        unnamed = {k: v for k, v in ORCA_TEMPLATE.items() if k != "name"}
        with self.assertRaisesRegex(ValueError, "no name"):
            est.estimate(DATA, engines(1), unnamed, {"geometry": CAFFEINE})
        other = est.estimate(DATA, engines(1), dict(ORCA_TEMPLATE, name="Saddle Calculation"), {"geometry": CAFFEINE})
        self.assertEqual(other["unknown_reason"], "no estimate for 'Saddle Calculation' jobs")

    def test_scale_and_errors(self):
        one = est.estimate(DATA, engines(1), ORCA_TEMPLATE, {"geometry": CAFFEINE})
        doubled = est.estimate(DATA, engines("2"), ORCA_TEMPLATE, {"geometry": CAFFEINE})
        self.assertAlmostEqual(doubled["seconds"], 2 * one["seconds"])
        for scale in (None, 0, "-1"):  # as on the job page: 1.0 unless the scale is above 0
            other = est.estimate(DATA, engines(scale), ORCA_TEMPLATE, {"geometry": CAFFEINE})
            self.assertEqual(other["scale"], 1.0)
            self.assertAlmostEqual(other["seconds"], one["seconds"])
            self.assertEqual(other["notes"], [])
        two_queues = {"orca": {"queues": {"slow": {"cpuEstScale": "3"}, "fast": {"cpuEstScale": "1"}}}}
        self.assertEqual(est.estimate(DATA, two_queues, ORCA_TEMPLATE, {"geometry": CAFFEINE})["scale"], 3)
        self.assertEqual(est.estimate(DATA, two_queues, ORCA_TEMPLATE, {"geometry": CAFFEINE},
                                      queue="fast")["scale"], 1)
        missing = est.estimate(DATA, {}, ORCA_TEMPLATE, {"geometry": CAFFEINE})
        self.assertIn("engine 'orca' isn't available to this account", missing["notes"])
        heavy = est.estimate(DATA, engines(1), ORCA_TEMPLATE, {"geometry": "U 0 0 0\nF 0 0 1"})
        self.assertEqual(heavy["formatted"], "unknown")
        self.assertIn("krypton", heavy["unknown_reason"])

    def test_job_cores(self):
        self.assertEqual(est.job_cores({}), 1)
        self.assertEqual(est.job_cores({"nodes": "2", "ppn": "4"}), 8)
        self.assertEqual(est.job_cores({"nproc": 6}), 6)
        self.assertEqual(est.job_cores({"nproc": 6}, nodes=2, ppn=3), 6)  # the arguments win
        self.assertEqual(est.job_cores({"nodes": 2, "ppn": 4}, ppn=16), 32)


class ServerVersionTest(unittest.TestCase):
    def test_check_server_version(self):
        for version in ("26.0.001e", "26", "27.1.002", " 30.0"):
            est.check_server_version(version)  # no error
        for version, found in (("25.0.004", "runs WebMO 25.0.004"), ("24", "runs WebMO 24"),
                               (None, "doesn't report its version"), ("", "doesn't report its version"),
                               ("beta", "runs WebMO beta")):
            with self.assertRaises(est.UnsupportedServerError) as cm:
                est.check_server_version(version)
            self.assertIn("require WebMO 26 or higher", str(cm.exception))
            self.assertIn(found, str(cm.exception))

    def test_fetch_data_refuses_old_servers_before_fetching(self):
        class OldRest:
            def get_status_info(self):
                return {"version": "25.0.004", "url_html": "https://server/webmo/"}
        with mock.patch("webmo.estimate.requests.get") as get:
            with self.assertRaises(est.UnsupportedServerError):
                est.fetch_data(OldRest())
            get.assert_not_called()

    def test_fetch_data_on_webmo_26(self):
        class NewRest:
            def get_status_info(self):
                return {"version": "26.0.001e", "url_html": "https://server/webmo/"}

        def fake_get(url, timeout=None):
            response = mock.Mock()
            response.json.return_value = {"url": url}
            return response
        with mock.patch("webmo.estimate.requests.get", side_effect=fake_get):
            data = est.fetch_data(NewRest())
        self.assertEqual(data["atom_rows"], {"url": "https://server/webmo/json/atom_rows.json"})
        self.assertEqual(sorted(data), ["atom_rows", "basis_counts", "method_scalings"])


class OfflineREST(WebMOREST):
    def __del__(self):
        pass  # there is no real session to log out of


class RestMethodTest(unittest.TestCase):
    """WebMOREST.estimate_job and get_templates, with the REST requests mocked."""

    def setUp(self):
        self.rest = OfflineREST.__new__(OfflineREST)  # skip the login in __init__
        self.rest._base_url = "https://server/rest.cgi"
        self.rest._auth = {"username": "alice", "token": "T"}
        self.status = {"version": "26.0.001e", "url_html": "https://server/webmo/"}
        self.requests = []
        test = self

        def fake_get(url, params=None, timeout=None, **kwargs):
            test.requests.append(url)
            response = mock.Mock(status_code=200)
            if url.endswith("/status"):
                response.json.return_value = test.status
            elif url.endswith("/engines"):
                response.json.return_value = {"engines": engines(1)}
            elif url.endswith("/templates/orca"):
                response.json.return_value = {"user": "alice", "templates": {
                    "Optimize + Vib Freq": {k: v for k, v in ORCA_TEMPLATE.items() if k != "name"},
                    "NMR": {"id": "orca/global/6", "name": "NMR", "variables": {}}}}
            elif "/json/" in url:
                response.json.return_value = DATA[url.rsplit("/", 1)[1][:-len(".json")]]
            else:
                raise AssertionError("unexpected request: %s" % url)
            return response
        for target in ("webmo.webmo_rest.requests.get", "webmo.estimate.requests.get"):
            patcher = mock.patch(target, side_effect=fake_get)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_get_templates_includes_names(self):
        templates = self.rest.get_templates("orca")
        self.assertEqual(templates["Optimize + Vib Freq"]["name"], "Optimize + Vib Freq")  # filled in
        self.assertEqual(templates["NMR"]["name"], "NMR")  # from the server

    def test_estimate_job(self):
        template = self.rest.get_templates("orca")["Optimize + Vib Freq"]
        variables = {"geometry": CAFFEINE, "method": "B3LYP"}
        result = self.rest.estimate_job(template, variables, nodes=1, ppn=8)
        self.assertEqual(result, est.estimate(DATA, engines(1), template, variables, cores=8))
        self.assertEqual(result["cores"], 8)
        self.assertEqual(result["recommend"], {"densityFitting": "on", "directSCF": "on"})
        self.assertEqual(self.rest.estimate_job(template, dict(variables, nproc=4))["cores"], 4)

    def test_data_is_fetched_once(self):
        template = self.rest.get_templates("orca")["Optimize + Vib Freq"]
        self.rest.estimate_job(template, {"geometry": CAFFEINE})
        self.rest.estimate_job(template, {"geometry": CAFFEINE}, ppn=4)
        self.assertEqual(sum(url.endswith("/status") for url in self.requests), 1)
        self.assertEqual(sum("/json/atom_rows.json" in url for url in self.requests), 1)
        self.assertEqual(sum(url.endswith("/engines") for url in self.requests), 2)  # queues can change

    def test_old_server(self):
        self.status = {"version": "25.0.004", "url_html": "https://server/webmo/"}
        template = self.rest.get_templates("orca")["Optimize + Vib Freq"]
        with self.assertRaisesRegex(UnsupportedServerError, "require WebMO 26 or higher"):
            self.rest.estimate_job(template, {"geometry": CAFFEINE})
        self.assertFalse(any("/json/" in url for url in self.requests))


JS_FILE = os.path.join(WEBMO_SOURCE, "javascript", "cpu_estimate.js")
HAS_BROWSER = importlib.util.find_spec("playwright") is not None and os.path.exists(JS_FILE)


@unittest.skipUnless(HAS_BROWSER, "needs Playwright with Chromium and WebMO's cpu_estimate.js")
class ParityTest(unittest.TestCase):
    """The port must give the same numbers as WebMO's own javascript over a large grid of inputs."""

    ENGINES = ["gaussian", "orca", "gamess", "nwchem", "psi", "qchem", "mopac", "xtb"]
    METHODS = ["SEMIEMPIRICAL", "HF", "DFT-GGA", "DFT-HYBRID", "MP2"]
    BASES = ["STO-3G", "3-21G", "6-31G(d)", "6-31G**", "6-31+G*", "6-311++G(3df,2pd)", "6-311G(2d,p)",
             "def2-SVP", "def2-TZVP", "cc-pVTZ", "aug-cc-pVDZ", "no-such-basis"]
    STOICHIOMETRIES = ["H2O", "C8H10N4O2", "CH3Cl", "KBr", "C6H4Br2", "UF6", "Xx2"]
    TEMPLATES = ["Molecular Energy", "Geometry Optimization", "Vibrational Frequencies", "Optimize + Vib Freq",
                 "NMR", "Bond Orders", "Excited States and UV-VIS"]

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        with open(JS_FILE) as f:
            source = f.read()
        data = load_data(os.path.join(WEBMO_SOURCE, "json"))
        cls.data = data
        # make the module callable as a plain script: data in place of the json imports,
        # the engine and scale as arguments instead of the script's URL parameters
        lines = [line for line in source.splitlines() if not line.startswith("import ")]
        body = "\n".join(lines).replace("new URL(import.meta.url).searchParams", "new URLSearchParams(params)")
        script = ("var iOS = false, android = false;\n"
                  "window.makeEstimator = function(params, ATOM_ROWS, BASIS_COUNTS, METHOD_SCALINGS) {\n%s\n"
                  "return {getCpuEstimate, getBasisCount, formatTime};\n};" % body)
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch()
        except Exception as e:
            cls.playwright.stop()
            raise unittest.SkipTest("Chromium can't start: %s" % str(e).splitlines()[0])
        cls.page = cls.browser.new_page()
        cls.page.set_content("<html><body></body></html>")
        cls.page.add_script_tag(content=script)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def javascript(self, function, engine, scale, calls):
        return self.page.evaluate("""([engine, scale, data, fn, calls]) => {
            const e = window.makeEstimator("engine=" + engine + "&scale=" + scale,
                                           data.atom_rows, data.basis_counts, data.method_scalings);
            return calls.map(args => {
                const v = e[fn](...args);
                return typeof v === "string" || Number.isFinite(v) ? v : null;
            });
        }""", [engine, scale, self.data, function, calls])

    def test_basis_counts(self):
        calls = [[s, b] for s in self.STOICHIOMETRIES for b in self.BASES]
        for (stoichiometry, basis), expected in zip(calls, self.javascript("getBasisCount", "orca", 1, calls)):
            ours = est.get_basis_count(self.data, stoichiometry, basis)
            if expected is None or expected < 0:
                self.assertEqual(ours, est.UNKNOWN, (stoichiometry, basis))
            else:
                self.assertEqual(ours, expected, (stoichiometry, basis))

    def test_cpu_estimates(self):
        compared = 0
        # only real elements: for an unknown symbol the javascript's basis count is NaN, and NaN ** 0 = 1
        # still gives a semiempirical estimate; the port reports unknown, and geometries never contain one
        stoichiometries = [s for s in self.STOICHIOMETRIES if s != "Xx2"]
        for engine, scale in itertools.product(self.ENGINES, (1, 1.7)):
            calls = [list(c) for c in itertools.product(self.TEMPLATES, stoichiometries, self.METHODS,
                                                        self.BASES, (False, True), (False, True), (1, 6))]
            for args, expected in zip(calls, self.javascript("getCpuEstimate", engine, scale, calls)):
                ours = est.get_cpu_estimate(self.data, engine, scale, *args)
                if expected is None or expected <= 0:
                    self.assertLessEqual(ours, 0, (engine, scale, args))
                else:
                    self.assertTrue(math.isclose(ours, expected, rel_tol=1e-9), (engine, scale, args, ours, expected))
                    compared += 1
        self.assertGreater(compared, 1000, "the grid should exercise many known estimates")

    def test_format_time(self):
        seconds = [0, 30, 59.9, 60, 89, 90, 149.9, 150, 599, 600, 1199, 1290, 1500, 1800, 2700, 5399, 5400,
                   5401, 7199, 9000, 12600, 36000, 100000, 1e6]
        calls = [[s] for s in seconds]
        for (value,), expected in zip(calls, self.javascript("formatTime", "orca", 1, calls)):
            self.assertEqual(est.format_time(value), expected, value)


if __name__ == "__main__":
    unittest.main()
