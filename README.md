# webmo-python
A Python-based interface to WebMO

## Rendering images outside Jupyter

`display_job_property()` shows WebMO's molecule, orbital, surface and spectrum views inside a Jupyter
notebook. `render_job_property()` produces the same images from any Python script, using WebMO's
viewers in a headless browser. It needs WebMO 24 or later and an optional dependency:

```bash
pip install 'webmo[render]'
python -m playwright install chromium
```

On Linux, Chromium also needs some system libraries. On Debian/Ubuntu, run
`python -m playwright install-deps chromium`. On RHEL/Rocky/Fedora, install them with dnf,
e.g. `dnf install mesa-libgbm libdrm nss atk`.

```python
from webmo import WebMOREST

rest = WebMOREST("https://server/cgi-bin/webmo/rest.cgi", "alice")
rest.render_job_property(123, "mo", "homo.png", property_index=12, width=600, height=600)
rest.render_job_property(123, "ir_spectrum", "ir.png")
png_bytes = rest.render_job_property(123, "esp")
```

The browser starts on the first call and is reused for later ones, so rendering many images is
fast; `rest.close_renderer()` shuts it down. `render_job_property()` is synchronous and cannot be
used inside a Jupyter notebook; use `await rest.display_job_property(...)` there.

## Estimating run time

`estimate_job()` gives the CPU-time estimate shown on WebMO's job submission page, and its
recommendations for density fitting and direct SCF. It is a port of WebMO's `cpu_estimate.js`
and uses the server's current timing data, which WebMO 26 and later provide; with an older
server, it raises `webmo.UnsupportedServerError`. It takes the same template and variables as
`generate_input()`, and the same `queue`, `nodes` and `ppn` as `submit_job()`.

```python
from webmo import WebMOREST

rest = WebMOREST("https://server/cgi-bin/webmo/rest.cgi", "alice")
template = rest.get_templates("orca")["Optimize + Vib Freq"]
variables = {"geometry": xyz, "method": "B3LYP", "basisSet": "def2-TZVP", "nproc": 8}
result = rest.estimate_job(template, variables, nodes=1, ppn=8)
print(result["formatted"])   # e.g. "~20-40 minutes", or "unknown" (see result["unknown_reason"])
print(result["recommend"])   # e.g. {"densityFitting": "on", "directSCF": "on"}

variables.update(result["recommend"])
job = rest.submit_job("caffeine", rest.generate_input(template, variables), "orca", nodes=1, ppn=8)
```

Recommendations are made only for settings not already in `variables`. Without `nodes` and
`ppn`, the cores come from the template's own variables (`nodes`/`ppn`, or `nproc`), else 1. For
a coordinate scan, pass `scan_points` (and `scan_optimized=True` for relaxed scans). WebMO
estimates common job types, methods and basis sets, for elements up to krypton; otherwise
`result["seconds"]` is -1. The timing data is fetched once per `WebMOREST` object.
