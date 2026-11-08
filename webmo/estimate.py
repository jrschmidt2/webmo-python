"""Estimate a WebMO job's CPU time, and recommend density fitting and direct SCF, as WebMO does.

A faithful port of WebMO's javascript/cpu_estimate.js, the estimate on the job submission page.
Its data comes from the server, so it is always current: <url_html>/json/method_scalings.json,
basis_counts.json and atom_rows.json. Option aliases (e.g. B3LYP -> DFT-HYBRID) come from the job
template (REST 'aliases'), and the per-server scale factor from get_engines() ('cpuEstScale').

Use it through WebMOREST.estimate_job, which fetches and caches that data:

    template = rest.get_templates("orca")["Optimize + Vib Freq"]
    result = rest.estimate_job(template, {"geometry": xyz, "method": "B3LYP"}, nodes=1, ppn=8)
    print(result["formatted"], result["recommend"])

estimate() here does the same from data already fetched (fetch_data, get_engines), without a server.
Requires WebMO 26 or higher, which serves the JSON data; older servers raise UnsupportedServerError.
"""

import math
import re

import requests

from .webmo_rest import UnsupportedServerError

SEMIEMPIRICAL_ENGINES = ("mopac", "xtb")
DUMMY_ATOMS = ("X", "XX", "BQ", "GH", "Q")
UNKNOWN = -1
MIN_WEBMO_VERSION = 26  # the first WebMO to serve the estimate data at <url_html>/json/


# --- port of cpu_estimate.js ------------------------------------------------------------------------
# Function names and structure follow the javascript, so the two can be compared side by side.
# The JSON stores most numbers as strings, which javascript converts implicitly; here num() does.

def num(value):
    return float(value)


def js_round(x):
    """Math.round: halves round up (Python's round() rounds halves to even)."""
    return math.floor(x + 0.5)


def parse_stoichiometry(stoichiometry):
    counts = {}
    for atom, count in re.findall(r"([A-Z][a-z]*)(\d*)", stoichiometry):
        counts[atom] = counts.get(atom, 0) + (int(count) if count else 1)
    return counts


def calculate_pople_basis_functions(basis_name):
    basis_name = re.sub(r"\s+", "", basis_name.upper())

    zeta = 1
    zeta_match = re.search(r"-(\d+)\+*G", basis_name)
    if zeta_match:
        zeta = len(zeta_match.group(1))

    is_cartesian = re.search(r"(3-21|6-31|6-311)", basis_name) is not None
    num_d = 6 if is_cartesian else 5
    num_f = 10 if is_cartesian else 7

    diffuse_heavy = diffuse_light = 0
    if "++" in basis_name:
        diffuse_heavy, diffuse_light = 4, 1
    elif "+" in basis_name:
        diffuse_heavy = 4

    heavy_d = heavy_f = light_p = light_d = 0
    if "**" in basis_name:
        heavy_d, light_p = 1, 1
    elif "*" in basis_name:
        heavy_d = 1

    pol_match = re.search(r"\((.*?)\)", basis_name)
    if pol_match:
        pol_parts = pol_match.group(1).split(",")
        heavy_pol = pol_parts[0] if len(pol_parts) > 0 else ""
        light_pol = pol_parts[1] if len(pol_parts) > 1 else ""

        def extract_count(text, shell):
            match = re.search(r"(\d*)" + shell, text)
            if match:
                return 1 if match.group(1) == "" else int(match.group(1))
            return 0

        heavy_d = max(heavy_d, extract_count(heavy_pol, "D"))
        heavy_f = max(heavy_f, extract_count(heavy_pol, "F"))
        light_p = max(light_p, extract_count(light_pol, "P"))
        light_d = max(light_d, extract_count(light_pol, "D"))

    base_r1 = 1 * zeta
    base_r2 = 1 + 4 * zeta
    base_r3 = 5 + 4 * zeta
    base_r4 = 9 + 4 * zeta + num_d * zeta

    extra_r1 = diffuse_light + light_p * 3 + light_d * num_d
    extra_heavy = diffuse_heavy + heavy_d * num_d + heavy_f * num_f

    return [base_r1 + extra_r1, base_r2 + extra_heavy, base_r3 + extra_heavy, base_r4 + extra_heavy]


def get_basis_count(data, stoichiometry, basis):
    atom_counts = parse_stoichiometry(stoichiometry)
    standardized_basis = basis.upper()
    is_pople_style = re.match(r"^\d", standardized_basis) is not None

    if not is_pople_style and standardized_basis not in data["basis_counts"]:
        return UNKNOWN
    counts = (calculate_pople_basis_functions(standardized_basis) if is_pople_style
              else [int(num(c)) for c in data["basis_counts"][standardized_basis]])

    basis_count = 0
    for atom, atom_count in atom_counts.items():
        row = data["atom_rows"].get(atom)
        if row is None or row > 4 or row <= 0:  # javascript yields NaN for unknown elements: also "unknown"
            return UNKNOWN
        basis_count += counts[row - 1] * atom_count
    return basis_count


def get_atom_count(stoichiometry):
    return sum(parse_stoichiometry(stoichiometry).values())


def get_cpu_estimate(data, engine, engine_scale, template, stoichiometry, method, basis, density_fitting,
                     unrestricted, cores, scan=None):
    """Estimated seconds, or UNKNOWN. scan = (num_points, is_opt) for 'Coordinate Scan'."""
    scalings = data["method_scalings"]
    natoms = get_atom_count(stoichiometry)
    global_scale_factor = num(scalings["_global_scale_factor"])

    basis_count = get_basis_count(data, stoichiometry, basis)
    if basis_count == UNKNOWN:
        return UNKNOWN

    if density_fitting:
        method = "RI-" + method

    if method not in scalings or engine not in scalings[method]:
        return UNKNOWN
    params = scalings[method][engine]

    def energy_time():
        nbasis_scaled = basis_count / num(scalings[method]["ref_nbasis"])
        cpu_estimate = (num(params["prefactor"]) * natoms ** num(params["scaling_natom"]) *
                        nbasis_scaled ** num(params["scaling_nbasis"]))
        if unrestricted:
            cpu_estimate *= 2
        if cores > 1:
            cpu_estimate /= cores ** 0.75  # assume sub-linear scaling
        return cpu_estimate * global_scale_factor * engine_scale

    def opt_time():
        first_cycle = energy_time()
        later_cycles = first_cycle * 0.4  # 40% of initial cost for subsequent SCFs
        nsteps_per_atom = num(scalings["nsteps_per_atom"].get(engine) or 1.0)
        est_ncycles = nsteps_per_atom * natoms
        return first_cycle + later_cycles * (est_ncycles - 1)

    def freq_time():
        analytical_hessian_factor = num(params.get("hessian_factor", 20))
        if params.get("hessian") == "analytical":
            return analytical_hessian_factor * energy_time()
        return 6 * natoms * energy_time() * 0.25  # 25% of initial SCF cost during displacements

    def giao_time():
        giao_factor = scalings["giao_factor"].get(engine)
        if giao_factor is None:  # undefined in javascript: NaN, shown as unknown
            return UNKNOWN
        return num(giao_factor) * energy_time()

    def scan_time():
        if not scan:
            return UNKNOWN  # the page reads the scan from MolEdit; here the caller must say
        num_points, is_opt = scan
        if is_opt:
            return opt_time() + 2 * energy_time() * 0.4 * (num_points - 1)
        return energy_time() + energy_time() * 0.4 * (num_points - 1)

    template = template.strip()
    if template in ("Molecular Energy", "Molecular Orbitals", "Natural Bond Orbitals", "Bond Orders"):
        return energy_time()
    if template == "Geometry Optimization":
        return opt_time()
    if template == "Vibrational Frequencies":
        return freq_time()
    if template == "Optimize + Vib Freq":
        return opt_time() + freq_time()
    if template == "Coordinate Scan":
        return scan_time()
    if template == "NMR":
        return giao_time()
    return UNKNOWN


def format_time(seconds):
    if seconds < 60:
        return "< 1 minute"
    if seconds < 60 * 90:
        est_minutes = js_round(seconds / 60)
        est_min = js_round(max(est_minutes * 0.7, 1))
        est_max = js_round(est_minutes * 1.3)
        if est_max > 20:
            est_min = js_round(est_min / 10) * 10
            est_max = js_round(est_max / 10) * 10
        if est_max - est_min == 0:
            return "~%d minute(s)" % est_max
        return "~%d-%d minutes" % (est_min, est_max)
    est_hours = js_round(seconds / 3600)
    est_min = js_round(max(est_hours * 0.7, 1))
    est_max = js_round(est_hours * 1.3)
    if est_max - est_min == 0:
        return "~%d hour(s)" % est_max
    return "~%d-%d hours" % (est_min, est_max)


def recommend_direct_scf(data, engine, basis_count, cores, density_fitting):
    """The page's rule; ORCA requires direct SCF with density fitting."""
    threshold = data["method_scalings"]["direct_scf_thresholds"].get(engine)
    over_threshold = threshold is not None and basis_count > num(threshold)
    return over_threshold or cores > 1 or (engine == "orca" and bool(density_fitting))


# --- reading the job settings, as updateCpuEstimate() reads the form ---------------------------------

def is_on(value):
    return value not in (None, "", False, 0, "0", "off")


def option_label(variable, value):
    """The visible label of a dropdown value (options are {label: value})."""
    for label, option_value in (variable.get("options") or {}).items():
        if option_value == value:
            return label
    return ""


def stoichiometry_from_geometry(geometry, atom_rows):
    """Formula (C, H first) from engine-formatted geometry text: first column is a symbol or atomic number."""
    symbols = list(atom_rows)  # periodic-table order, so index + 1 is the atomic number
    counts = {}
    for line in str(geometry).splitlines():
        tokens = line.replace(",", " ").split()
        if not tokens:
            continue
        token = re.sub(r"[^A-Za-z0-9]", "", tokens[0])
        symbol = None
        if token.isdigit():
            z = int(token)
            symbol = symbols[z - 1] if 0 < z <= len(symbols) else None
        else:
            match = re.match(r"([A-Za-z]{1,2})", token)
            if match:
                candidate = match.group(1).capitalize()
                if candidate.upper() in DUMMY_ATOMS:
                    continue
                if candidate in atom_rows:
                    symbol = candidate
                elif candidate[0] in atom_rows:  # labels such as "C1" or "H12"
                    symbol = candidate[0]
        if symbol:
            counts[symbol] = counts.get(symbol, 0) + 1
    first = [s for s in ("C", "H") if s in counts] if "C" in counts else []
    order = first + sorted(s for s in counts if s not in first)
    return "".join("%s%s" % (s, counts[s] if counts[s] > 1 else "") for s in order)


def job_settings(engine, template, variables):
    """(method, basis, unrestricted) the way the job page reads its form."""
    template_vars = template["variables"]

    def value(name):
        if name in variables:
            return str(variables[name])
        return str(template_vars.get(name, {}).get("default") or "")

    def alias(name, val):
        return (template_vars.get(name, {}).get("aliases") or {}).get(val, val)

    if engine in SEMIEMPIRICAL_ENGINES:
        return "SEMIEMPIRICAL", "STO-3G", None

    basis = alias("basisSet", value("basisSet"))

    # a functional dropdown counts only while the page enables it, for a DFT theory/method choice
    # (gamess.js: the label starts with 'DFT'; nwchem.js, psi.js: the value is 'dft')
    method_var = "theory" if "theory" in template_vars else "method"
    method_value = value(method_var)
    functional_enabled = "functional" in template_vars and (
        method_value.strip().lower() == "dft" or
        option_label(template_vars.get(method_var, {}), method_value).strip().upper().startswith("DFT"))
    if functional_enabled:
        method = alias("functional", value("functional"))
    else:
        method = alias(method_var, method_value)

    if "reference" in template_vars:  # Psi4
        unrestricted = value("reference") == "uhf"
    elif "unrestricted" not in template_vars:  # e.g. GAMESS: part of the theory
        unrestricted = re.search(r"UHF$", value("theory")) is not None
    elif template_vars["unrestricted"].get("type") == "checkbox":
        unrestricted = is_on(value("unrestricted"))
    else:
        selected = value("unrestricted")
        unrestricted = selected == "U" if selected else value("multiplicity") not in ("", "1")
    return method, basis, unrestricted


# --- fetching and the public API ---------------------------------------------------------------------

def fetch_data(rest):
    """WebMO's estimate data (method_scalings, basis_counts, atom_rows) from the server.

    Raises UnsupportedServerError if the server is older than WebMO 26.
    """
    status = rest.get_status_info()
    check_server_version(status.get("version"))
    base = status["url_html"].rstrip("/")
    data = {}
    for key in ("method_scalings", "basis_counts", "atom_rows"):
        response = requests.get("%s/json/%s.json" % (base, key), timeout=30)
        response.raise_for_status()
        data[key] = response.json()
    return data


def check_server_version(version):
    """Raises UnsupportedServerError unless version (e.g. '26.0.001e') is WebMO 26 or higher."""
    match = re.match(r"\s*(\d+)", str(version or ""))
    if not match or int(match.group(1)) < MIN_WEBMO_VERSION:
        found = "runs WebMO %s" % version if version else "doesn't report its version"
        raise UnsupportedServerError("Run time estimates require WebMO %d or higher; this server %s"
                                     % (MIN_WEBMO_VERSION, found))


def engine_scale(engines, engine, queue=None):
    """(cpuEstScale, note) for the chosen server or queue; like the page, 1.0 unless it is above 0.

    engines is get_engines(); queue defaults to the engine's first server or queue.
    """
    hosts = engines.get(engine, {})
    hosts = hosts.get("servers") or hosts.get("queues") or {}
    if not hosts:
        return 1.0, "engine '%s' isn't available to this account" % engine
    host = queue if queue in hosts else next(iter(hosts))
    scale = num(hosts[host].get("cpuEstScale") or 0)
    return (scale if scale > 0 else 1.0), None


def job_cores(variables, nodes=None, ppn=None):
    """Total cores, nodes x ppn: the arguments if given, else the template's own variables
    (Gaussian nodes/ppn, ORCA nproc), else 1."""
    nodes = int(nodes or variables.get("nodes") or 1)
    ppn = int(ppn or variables.get("ppn") or variables.get("nproc") or 1)
    return max(nodes, 1) * max(ppn, 1)


def estimate(data, engines, template, variables, cores=1, queue=None, scan_points=None, scan_optimized=False,
             stoichiometry=None):
    """Estimate run time and WebMO's density-fitting / direct-SCF recommendations for a planned job.

    data is fetch_data(rest), engines is rest.get_engines(), template is one from rest.get_templates()
    (its 'name' is the job type and its 'id' gives the engine), and variables are those for
    generate_input. stoichiometry (e.g. 'C8H10N4O2') replaces the formula read from the geometry.
    See WebMOREST.estimate_job for the result.
    """
    template_name = template.get("name")
    if not template_name:
        raise ValueError("The template has no name; use one from get_templates()")
    engine = template["id"].split("/")[0].lower()
    template_vars = template["variables"]

    scale, scale_note = engine_scale(engines, engine, queue)
    stoichiometry = stoichiometry or stoichiometry_from_geometry(variables.get("geometry", ""), data["atom_rows"])
    method, basis, unrestricted = job_settings(engine, template, variables)
    notes = [scale_note] if scale_note else []
    scan = (scan_points, scan_optimized) if scan_points else None

    def run(density_fitting):
        return get_cpu_estimate(data, engine, scale, template_name, stoichiometry, method, basis,
                                density_fitting, unrestricted, cores, scan)

    result = {"stoichiometry": stoichiometry, "natoms": get_atom_count(stoichiometry),
              "nbasis": get_basis_count(data, stoichiometry, basis), "method": method, "basis": basis.upper(),
              "unrestricted": bool(unrestricted), "cores": cores, "scale": scale, "recommend": {}, "notes": notes}

    density_fitting = is_on(variables.get("densityFitting"))
    if "densityFitting" in template_vars and "densityFitting" not in variables:
        # like the page, recommend it only when both estimates exist, on whether it is faster
        conventional, fitted = run(False), run(True)
        result["density_fitting_seconds"] = {"off": conventional, "on": fitted}
        if conventional > 0 and fitted > 0:
            density_fitting = fitted < conventional
            result["recommend"]["densityFitting"] = "on" if density_fitting else ""
    result["density_fitting"] = density_fitting

    seconds = run(density_fitting)
    result["seconds"] = seconds
    result["formatted"] = format_time(seconds) if seconds > 0 else "unknown"
    if seconds <= 0:
        result["unknown_reason"] = unknown_reason(data, engine, template_name, stoichiometry, method, basis,
                                                  density_fitting, scan)

    if "directSCF" in template_vars and "directSCF" not in variables:
        direct = recommend_direct_scf(data, engine, result["nbasis"], cores, density_fitting)
        result["recommend"]["directSCF"] = "on" if direct else ""
    return result


def unknown_reason(data, engine, template_name, stoichiometry, method, basis, density_fitting, scan):
    if not stoichiometry:
        return "no atoms found in the geometry"
    if get_basis_count(data, stoichiometry, basis) == UNKNOWN:
        rows = data["atom_rows"]
        heavy = [a for a in parse_stoichiometry(stoichiometry) if not 0 < rows.get(a, 0) <= 4]
        if heavy:
            return "estimates cover elements up to krypton only (%s)" % ", ".join(heavy)
        return "no basis function data for basis set '%s'" % basis
    key = ("RI-" if density_fitting else "") + method
    if key not in data["method_scalings"] or engine not in data["method_scalings"][key]:
        return "no timing data for %s with %s" % (key, engine)
    if template_name.strip() == "Coordinate Scan" and not scan:
        return "pass the number of scan points (scan_points)"
    return "no estimate for '%s' jobs" % template_name.strip()
