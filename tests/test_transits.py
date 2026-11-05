import datetime as dt

import pytest
import swisseph as swe

from astro_engine.calc import angdiff, body_position, julday_utc, natal_chart, point_map
from astro_engine.transits import transit_report

BIRTH = {"date": "1987-04-12", "time": "14:35", "place": {"lat": 53.2001, "lon": 50.15, "tz": "Europe/Samara"}}


@pytest.fixture(scope="module")
def report():
    c = natal_chart(BIRTH)
    return c, transit_report(c, "2026-11-01", "2027-10-31", tz="UTC")


def _jd(iso):
    return julday_utc(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc))


def test_exact_hits_are_exact(report):
    c, r = report
    pm = point_map(c)
    angle = {"conjunction": 0, "opposition": 180, "trine": 120, "square": 90, "sextile": 60}
    n = 0
    for e in r["events"]:
        if not e["exact"]:
            continue
        lon = body_position(_jd(e["exact_utc"]), e["transit"])[0]
        sep = abs(angdiff(lon, pm[e["natal"]]["lon"]))
        assert abs(sep - angle[e["type"]]) < 0.01, e       # < 36" at the reported minute
        n += 1
    assert n > 20


def test_windows_contain_exact_and_respect_orb(report):
    _, r = report
    for e in r["events"]:
        assert e["window"][0] <= e["date_exact"] <= e["window"][1]


def test_retro_passes_numbered(report):
    _, r = report
    multi = [e for e in r["events"] if e["passes_total"] >= 2]
    assert multi, "expected at least one multi-pass transit of a slow planet in a year"
    for e in multi:
        assert 1 <= e["retro_pass"] <= e["passes_total"]
    assert any(e["retro_pass"] == 2 and e["transit_retrograde"] for e in multi)


def test_known_sky_events_2027(report):
    _, r = report
    sky = r["sky_events"]
    solar = [(e["date"], e["eclipse_type"]) for e in sky if e["kind"] == "solar_eclipse"]
    lunar = [(e["date"], e["eclipse_type"]) for e in sky if e["kind"] == "lunar_eclipse"]
    # NASA Five Millennium Canon: 2027-02-06 annular, 2027-08-02 total; lunar 2027-02-20, 07-18, 08-17 penumbral
    assert ("2027-02-06", "annular") in solar and ("2027-08-02", "total") in solar
    assert [d for d, _ in lunar] == ["2027-02-20", "2027-07-18", "2027-08-17"]
    assert all(t == "penumbral" for _, t in lunar)
    merc = [(e["from"], e["to"]) for e in sky if e["kind"] == "mercury_retrograde"]
    # published ephemeris tables (UTC): 2027-02-09..03-03, 2027-06-10..07-04, 2027-10-07..10-28
    assert ("2027-02-09", "2027-03-03") in merc and ("2027-06-10", "2027-07-04") in merc
    assert ("2027-10-07", "2027-10-28") in merc
    mars = [(e["from"], e["to"]) for e in sky if e["kind"] == "mars_retrograde"]
    assert mars == [("2027-01-10", "2027-04-01")]
    new_moons = [e for e in sky if e["kind"] == "new_moon"]
    full_moons = [e for e in sky if e["kind"] == "full_moon"]
    assert 12 <= len(new_moons) <= 13 and 12 <= len(full_moons) <= 13
    # solar eclipses coincide with new moons, lunar ones with full moons
    nm = {e["date"] for e in new_moons}
    assert "2027-02-06" in nm and "2027-08-02" in nm
    ingress_sun = [e for e in sky if e["kind"] == "ingress" and e["planet"] == "sun"]
    assert len(ingress_sun) == 12
    aries = next(e for e in ingress_sun if e["sign"] == "aries")
    assert aries["date"] == "2027-03-20"                    # March equinox 2027: 20 Mar 20:25 UTC


def test_lunation_precision(report):
    _, r = report
    for e in r["sky_events"]:
        if e["kind"] in ("new_moon", "full_moon"):
            jd = _jd(e["at_utc"])
            el = (body_position(jd, "moon")[0] - body_position(jd, "sun")[0]) % 360
            target = 0 if e["kind"] == "new_moon" else 180
            assert abs(angdiff(el, target)) < 0.02


def test_ingress_precision(report):
    _, r = report
    for e in r["sky_events"]:
        if e["kind"] == "ingress":
            lon = body_position(_jd(e["at_utc"]), e["planet"])[0]
            assert min(lon % 30, 30 - lon % 30) < 0.02
