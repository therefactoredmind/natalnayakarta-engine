"""Reference charts of public figures: astrotheme.com published positions (rounded to 1′).

Data: tests/data/reference_charts.json (birth data and positions copied verbatim from the public pages,
Rodden rating as shown there; coordinates chosen as documented in each record's coord_note).
Tolerances (task spec): planets <= 1′, Asc/MC <= 2′. The published values are rounded to whole arc-minutes,
so a perfect engine can show up to 0.5′ here.

Note: astrotheme also uses Swiss Ephemeris, so this mainly validates *our time-zone handling, LMT,
coordinates and house maths*; the ephemeris itself is independently validated against astronomy-engine.
"""
import json
import os
import re

import pytest

from astro_engine.calc import angdiff, natal_chart, point_map
from astro_engine.constants import SIGNS

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = json.load(open(os.path.join(HERE, "data", "reference_charts.json"), encoding="utf-8"))
BODIES = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "true_node"]
RESULTS = {}


def parse(s):
    m = re.match(r"(\d+)°(\d+)'\s+(\w+)", s)
    return int(m[1]) + int(m[2]) / 60 + 30 * SIGNS.index(m[3].lower())


def chart_for(r):
    return natal_chart({"date": r["date"], "time": r["time"], "time_known": True,
                        "place": {"lat": r["lat"], "lon": r["lon"], "tz": r["tz"]}})


def deviations(r):
    pm = point_map(chart_for(r))
    return {k: abs(angdiff(pm[k]["lon"], parse(v))) * 60 for k, v in r["positions"].items() if k in pm}


@pytest.mark.parametrize("r", CASES, ids=[c["name"] for c in CASES])
def test_reference_chart(r):
    dev = deviations(r)
    RESULTS[r["name"]] = dev
    if r.get("known_discrepancy"):
        # Documented disagreement: keep it visible — fail loudly if it silently disappears or changes.
        assert dev["moon"] > 20, "known discrepancy vanished — update TIMEZONES.md"
        pytest.xfail(r["known_discrepancy"])
    for k in BODIES:
        if k in dev:
            assert dev[k] <= 1.0, f"{r['name']} {k}: {dev[k]:.2f}′"
    if r["check_angles"]:
        for k in ("asc", "mc"):
            assert dev[k] <= 2.0, f"{r['name']} {k}: {dev[k]:.2f}′"


def test_summary_print():
    """Prints the max deviations (run with -s)."""
    strict = [c for c in CASES if c["strict"]]
    dev = {c["name"]: deviations(c) for c in strict}
    planets = max(v for d in dev.values() for k, v in d.items() if k in BODIES)
    angles = max(v for c in strict if c["check_angles"] for k, v in dev[c["name"]].items() if k in ("asc", "mc"))
    print(f"\nreference charts AA/A: {len(strict)} cases, angles checked: {sum(c['check_angles'] for c in strict)}; "
          f"max planet dev {planets:.2f}′, max Asc/MC dev {angles:.2f}′")
    assert planets <= 1.0 and angles <= 2.0
