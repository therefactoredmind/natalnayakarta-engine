"""Without .se1 files Swiss Ephemeris falls back to the built-in Moshier ephemeris.
Check that this is detected/reported and that the precision stays far inside the 1' budget."""
import json
import os
import subprocess
import sys

from astro_engine.calc import natal_chart, point_map

CODE = r"""
import json
from astro_engine.calc import natal_chart
c = natal_chart({"date": "1987-04-12", "time": "14:35", "place": {"lat": 53.2001, "lon": 50.15, "tz": "Europe/Samara"}})
print(json.dumps({"eph": c["engine"]["ephemeris"], "warnings": c["warnings"], "points": {p["id"]: p["lon"] for p in c["points"]}}))
"""


def test_moshier_fallback(tmp_path):
    env = dict(os.environ, ASTRO_EPHE_PATH=str(tmp_path))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, "-c", CODE], cwd=here, env=env, capture_output=True, text=True, check=True)
    m = json.loads(out.stdout.strip().splitlines()[-1])
    assert "Moshier" in m["eph"]
    assert "chiron_unavailable" in m["warnings"]          # Chiron needs seas_18.se1
    ref = point_map(natal_chart({"date": "1987-04-12", "time": "14:35",
                                 "place": {"lat": 53.2001, "lon": 50.15, "tz": "Europe/Samara"}}))
    for pid, lon in m["points"].items():
        d = abs((lon - ref[pid]["lon"] + 180) % 360 - 180) * 3600
        assert d < 5.0, (pid, d)                           # arcseconds
