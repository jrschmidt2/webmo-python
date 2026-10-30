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
