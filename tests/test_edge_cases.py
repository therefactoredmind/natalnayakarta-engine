import time

import pytest

from astro_engine.calc import natal_chart, point_map, body_position, julday_utc, sign_of
from astro_engine.transits import stations, transit_report

MOSCOW = {"lat": 55.7558, "lon": 37.6173, "tz": "Europe/Moscow"}


def chart(date, time_, place, **kw):
    d = {"date": date, "time": time_, "time_known": time_ is not None, "place": place}
    d.update(kw)
    return natal_chart(d)


def test_midnight_date_change_utc_previous_day():
    c = chart("2000-01-01", "00:30", MOSCOW)
    assert c["utc"] == "1999-12-31T21:30:00Z"
    c2 = chart("1995-06-01", "02:10", {"lat": 43.1155, "lon": 131.8855, "tz": "Asia/Vladivostok"})
    assert c2["utc"] == "1995-05-31T15:10:00Z"           # Vladivostok summer 1995 = UTC+11
    # one minute apart across local midnight -> Moon moves ~0.5', Asc ~0.25°
    a = point_map(chart("2000-01-01", "00:00", MOSCOW))
    b = point_map(chart("1999-12-31", "23:59", MOSCOW))
    assert 0 < (a["moon"]["lon"] - b["moon"]["lon"]) * 60 < 1.0


def test_west_longitude_date_change_next_day():
    c = chart("1990-12-31", "20:00", {"lat": 40.7128, "lon": -74.006, "tz": "America/New_York"})
    assert c["utc"] == "1991-01-01T01:00:00Z"


@pytest.mark.parametrize("name,lat,lon,tz", [("Murmansk", 68.9585, 33.0827, "Europe/Moscow"),
                                             ("Norilsk", 69.3535, 88.2027, "Asia/Krasnoyarsk"),
                                             ("Vorkuta", 67.4974, 64.0611, "Europe/Moscow")])
@pytest.mark.parametrize("hs", ["P", "K"])
def test_polar_fallback(name, lat, lon, tz, hs):
    c = chart("1985-01-15", "10:00", {"lat": lat, "lon": lon, "tz": tz}, house_system=hs)
    assert c["engine"]["house_system_used"] == "O"
    assert "house_system_fallback" in c["warnings"]
    assert len(c["houses"]) == 12
    pm = point_map(c)
    assert abs(c["houses"][0]["cusp_lon"] - pm["asc"]["lon"]) < 1e-6
    assert abs(c["houses"][9]["cusp_lon"] - pm["mc"]["lon"]) < 1e-6


def test_polar_whole_sign_no_fallback():
    c = chart("1985-01-15", "10:00", {"lat": 68.9585, "lon": 33.0827, "tz": "Europe/Moscow"}, house_system="W")
    assert c["engine"]["house_system_used"] == "W" and "house_system_fallback" not in c["warnings"]
    assert all(h["cusp_lon"] % 30 == 0 for h in c["houses"])


def test_placidus_works_below_polar_circle():
    c = chart("1985-01-15", "10:00", {"lat": 66.0, "lon": 33.0, "tz": "Europe/Moscow"})
    assert c["engine"]["house_system_used"] == "P"


def test_unknown_time():
    c = natal_chart({"date": "1987-04-12", "time": None, "time_known": False,
                     "place": {"lat": 53.2001, "lon": 50.15, "tz": "Europe/Samara"}})
    assert c["houses"] == [] and c["angles"] is None
    ids = [p["id"] for p in c["points"]]
    assert "asc" not in ids and "mc" not in ids
    assert all(p["house"] is None for p in c["points"])
    assert "time_unknown" in c["time_warnings"]
    assert c["summary"]["big_three"]["asc"] is None
    assert c["summary"]["moon_sign_range"] == ["virgo", "libra"]   # Moon enters Libra that day
    assert c["utc"] == "1987-04-12T07:00:00Z"                       # computed for 12:00 local (UTC+5)
    assert all(a.get("uncertain") for a in c["aspects"] if "moon" in (a["a"], a["b"]))


def _find_sun_at(target_lon, jd_guess):
    lo, hi = jd_guess - 3, jd_guess + 3
    for _ in range(60):
        m = (lo + hi) / 2
        d = (body_position(m, "sun")[0] - target_lon + 180) % 360 - 180
        lo, hi = (m, hi) if d < 0 else (lo, m)
    return (lo + hi) / 2


def test_planet_at_29_59_stays_in_sign():
    import swisseph as swe
    jd_ingress = _find_sun_at(30.0, swe.julday(1990, 4, 20, 12))
    jd = jd_ingress - 50 / 1440                    # Sun ~2' before Taurus ingress
    y, m, d, h = swe.revjul(jd)
    hh, mm = int(h), int(round((h - int(h)) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    c = chart(f"{y:04d}-{m:02d}-{d:02d}", f"{hh:02d}:{mm:02d}", {"lat": 51.5, "lon": 0.0, "tz": "UTC"})
    sun = point_map(c)["sun"]
    assert sun["sign"] == "aries" and 29.95 < sun["deg_in_sign"] < 30.0
    assert sun["dms"].startswith("29°5")
    y2, m2, d2, h2 = swe.revjul(jd_ingress + 5 / 1440)
    later = point_map(chart(f"{y2:04d}-{m2:02d}-{d2:02d}", f"{int(h2):02d}:{int((h2 % 1) * 60):02d}",
                            {"lat": 51.5, "lon": 0.0, "tz": "UTC"}))
    assert later["sun"]["sign"] == "taurus" and later["sun"]["deg_in_sign"] < 0.01


def test_retro_station():
    import swisseph as swe
    jd0 = swe.julday(1990, 1, 1, 0)
    st = stations("mercury", jd0, jd0 + 200)
    t, kind = st[0]
    from astro_engine.transits import _jd_to_dt
    dt_ = _jd_to_dt(t)
    before = point_map(chart(dt_.strftime("%Y-%m-%d"), (dt_.replace(second=0)).strftime("%H:%M"), {"lat": 0, "lon": 0, "tz": "UTC"}))
    assert before["mercury"].get("stationary") is True
    assert abs(before["mercury"]["speed"]) < 0.01


def test_performance_natal_and_year():
    natal_chart({"date": "1987-04-12", "time": "14:35", "place": {"lat": 53.2, "lon": 50.15, "tz": "Europe/Samara"}})
    t = time.perf_counter()
    for _ in range(20):
        c = natal_chart({"date": "1987-04-12", "time": "14:35", "place": {"lat": 53.2, "lon": 50.15, "tz": "Europe/Samara"}})
    natal_ms = (time.perf_counter() - t) / 20 * 1000
    t = time.perf_counter()
    transit_report(c, "2026-11-01", "2027-10-31")
    year_s = time.perf_counter() - t
    print(f"natal {natal_ms:.1f} ms, yearly transit report {year_s:.2f} s")
    assert natal_ms < 300 and year_s < 3


def test_user_offset_override():
    base = {"date": "1990-01-15", "time": "12:00", "place": {"lat": 53.2, "lon": 50.15, "tz": "Europe/Samara"}}
    a = natal_chart(base)
    b = natal_chart(dict(base, utc_offset_override=4))
    assert a["utc"] == "1990-01-15T09:00:00Z" and b["utc"] == "1990-01-15T08:00:00Z"
    assert "utc_offset_user_override" in b["time_warnings"] and b["tz_details"]["tzdb_utc_offset_hours"] == 3


def test_ambiguous_fold_in_input():
    base = {"date": "2014-10-26", "time": "01:30", "place": MOSCOW}
    assert natal_chart(base)["utc"] == "2014-10-25T21:30:00Z"
    assert natal_chart(dict(base, fold=1))["utc"] == "2014-10-25T22:30:00Z"
