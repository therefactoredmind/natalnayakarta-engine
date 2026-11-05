"""Independent cross-check against astronomy-engine (MIT; VSOP87 + ELP/MPP02-derived Moon + numeric Pluto,
IAU 2000B nutation) — a code base that shares nothing with Swiss Ephemeris.

Two parts: (1) 400 pseudo-random moments 1800-2100 at random latitudes |lat|<=66; (2) the reference charts.
Planets must agree within 1', Asc/MC within 2'. astronomy-engine's own stated accuracy is ~1', so the
max deviations printed by the test are mostly astronomy-engine's error, not ours.
Delta-T: both libraries extrapolate Delta-T differently for future dates (2099: 93 s vs 200 s -> ~1' for the Moon),
so bodies are compared at equal Terrestrial Time (astronomy-engine's UT shifted by the Delta-T difference);
Asc/MC are compared at the original UT.
"""
import datetime as dt
import json
import os
import random
import shutil
import subprocess

import pytest

from astro_engine.calc import compute_houses, julday_utc, body_position, angdiff
from astro_engine.constants import PLANETS

HERE = os.path.dirname(os.path.abspath(__file__))
CC = os.path.join(HERE, "crosscheck")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE or not os.path.isdir(os.path.join(CC, "node_modules", "astronomy-engine")),
                                reason="node + astronomy-engine not installed (cd tests/crosscheck && npm ci)")


def run_ae(cases):
    import swisseph as swe
    for c in cases:
        t = dt.datetime.strptime(c["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        c["dt_se"] = swe.deltat(julday_utc(t)) * 86400.0
    out = subprocess.run([NODE, os.path.join(CC, "ae_positions.js")], input=json.dumps(cases), capture_output=True,
                         text=True, check=True)
    return json.loads(out.stdout)


def compare(cases, ae):
    worst = {}
    for c in cases:
        t = dt.datetime.strptime(c["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        jd = julday_utc(t)
        mine = {p: body_position(jd, p)[0] for p in PLANETS}
        if c["lat"] is not None:
            _, asc, mc, _, _ = compute_houses(jd, c["lat"], c["lon"], "P")
            mine.update(asc=asc, mc=mc)
        for k, v in mine.items():
            d = abs(angdiff(v, ae[c["id"]][k])) * 60
            if d > worst.get(k, (0, None))[0]:
                worst[k] = (d, c["id"])
    return worst


def random_cases(n=400, seed=42):
    rnd = random.Random(seed)
    t0 = dt.datetime(1800, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t1 = dt.datetime(2099, 12, 31, tzinfo=dt.timezone.utc).timestamp()
    cases = []
    for i in range(n):
        t = dt.datetime.fromtimestamp(rnd.uniform(t0, t1), dt.timezone.utc).replace(microsecond=0)
        cases.append({"id": f"r{i}", "utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "lat": round(rnd.uniform(-66, 66), 4),
                      "lon": round(rnd.uniform(-180, 180), 4)})
    return cases


def test_random_moments_1800_2100():
    cases = random_cases()
    worst = compare(cases, run_ae(cases))
    report = {k: round(v[0], 3) for k, v in worst.items()}
    print("\nmax deviation vs astronomy-engine, arcmin:", report)
    for k, (d, cid) in worst.items():
        limit = 2.0 if k in ("asc", "mc") else 1.0
        assert d <= limit, (k, d, cid)


def test_reference_charts_vs_astronomy_engine():
    from astro_engine.calc import natal_chart
    ref = json.load(open(os.path.join(HERE, "data", "reference_charts.json"), encoding="utf-8"))
    cases = []
    for r in ref:
        c = natal_chart({"date": r["date"], "time": r["time"], "place": {"lat": r["lat"], "lon": r["lon"], "tz": r["tz"]}})
        cases.append({"id": r["name"], "utc": c["utc"], "lat": r["lat"], "lon": r["lon"]})
    worst = compare(cases, run_ae(cases))
    print("\nreference charts vs astronomy-engine, max arcmin:", {k: round(v[0], 3) for k, v in worst.items()})
    for k, (d, cid) in worst.items():
        assert d <= (2.0 if k in ("asc", "mc") else 1.0), (k, d, cid)
