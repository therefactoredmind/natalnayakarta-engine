"""Transits to a natal chart + sky events (stations, eclipses, lunations, ingresses).

Output = docs/CHART_SCHEMA.md `TransitReport`.

Method
------
* Transiting longitudes are sampled once per day (UT 00:00) over the period extended by a
  margin (so windows of slow planets that started before the period are complete).
* For every (transiting planet, natal point, aspect, branch +/-angle) the signed distance
  f(t) = angdiff(transit(t), natal + branch) is examined:
    - an *episode* is a maximal run of days with |f| <= orb_max, its ends are refined by
      bisection to ~1 minute -> ``window``;
    - each sign change of f inside the episode is an exact hit, refined by bisection to
      ~1 minute -> ``date_exact``; hits are numbered ``retro_pass`` 1..n (n=3 for a classic
      direct-retro-direct triple pass);
    - an episode without an exact hit (a station inside the orb) yields one event with
      ``exact: false`` at the moment of minimal orb.
* Dates are given in the report time zone (default: natal birth zone); `*_utc` fields keep UTC.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Dict, List, Optional, Tuple

import swisseph as swe

from . import constants as C
from .calc import (LOCK, angdiff, body_position, house_of, house_cusps, julday_utc, norm360, point_map,
                   sign_of, FLAGS)
from .timezones import get_zone

TRANSIT_PLANETS_DEFAULT = ["mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
NATAL_TARGETS_DEFAULT = C.PLANETS + ["asc", "mc"]
TRANSIT_ORB = {"sun": 1.0, "mercury": 1.0, "venus": 1.0, "mars": 1.0, "jupiter": 1.0, "saturn": 1.0,
               "uranus": 1.0, "neptune": 1.0, "pluto": 1.0, "chiron": 1.0, "true_node": 1.0}
W_TRANSIT = {"pluto": 1.0, "neptune": 0.95, "uranus": 0.9, "saturn": 0.85, "jupiter": 0.6, "chiron": 0.5,
             "true_node": 0.5, "mars": 0.35, "sun": 0.25, "venus": 0.25, "mercury": 0.2}
W_NATAL = {"sun": 1.0, "moon": 1.0, "asc": 1.0, "mc": 1.0, "mercury": 0.8, "venus": 0.8, "mars": 0.8,
           "jupiter": 0.6, "saturn": 0.6, "uranus": 0.4, "neptune": 0.4, "pluto": 0.4,
           "true_node": 0.4, "chiron": 0.4, "lilith": 0.3}
W_ASPECT = {"conjunction": 1.0, "opposition": 0.9, "square": 0.9, "trine": 0.6, "sextile": 0.5}
MINUTE = 1.0 / 1440.0
SWE_SPEED = {"mercury": swe.MERCURY, "venus": swe.VENUS, "mars": swe.MARS}


def _jd_to_dt(jd: float) -> dt.datetime:
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    base = dt.datetime(y, m, d, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(hours=h)


def _bisect(f: Callable[[float], float], a: float, b: float, fa: float, tol: float = MINUTE) -> float:
    """Root of f in [a,b] given sign(f(a)) != sign(f(b))."""
    while b - a > tol:
        m = (a + b) / 2
        fm = f(m)
        if (fm < 0) == (fa < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


class _Fmt:
    def __init__(self, tz: str):
        self.z = get_zone(tz)

    def date(self, jd: float) -> str:
        return _jd_to_dt(jd).astimezone(self.z).date().isoformat()

    def utc(self, jd: float) -> str:
        return _jd_to_dt(jd).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lon(pid: str) -> Callable[[float], float]:
    return lambda jd: body_position(jd, pid)[0]


def transit_events(natal: Dict, jd0: float, jd1: float, fmt: _Fmt, planets: List[str], targets: List[str],
                   orbs: Dict[str, float]) -> List[Dict]:
    npts = point_map(natal)
    targets = [t for t in targets if t in npts]
    margin = 420.0
    days = int(jd1 - jd0 + 2 * margin) + 2
    start = jd0 - margin
    events = []
    for tp in planets:
        lonf = _lon(tp)
        series = [lonf(start + i) for i in range(days)]
        orb_max = orbs.get(tp, 1.0)
        for nt in targets:
            nl = npts[nt]["lon"]
            for typ, ang, ru in C.ASPECTS:
                branches = [0.0] if ang in (0, 180) else [ang, -ang]
                for br in branches:
                    target = norm360(nl + (180.0 if ang == 180 else br))
                    f = lambda jd, target=target: angdiff(lonf(jd), target)
                    vals = [angdiff(x, target) for x in series]
                    i = 0
                    while i < days:
                        if abs(vals[i]) > orb_max:
                            i += 1
                            continue
                        j = i
                        while j + 1 < days and abs(vals[j + 1]) <= orb_max:
                            j += 1
                        # refine window edges
                        g = lambda jd: abs(f(jd)) - orb_max
                        w0 = start + i if i == 0 else _bisect(g, start + i - 1, start + i, g(start + i - 1))
                        w1 = start + j if j == days - 1 else _bisect(g, start + j, start + j + 1, g(start + j))
                        hits = []
                        for k in range(max(i - 1, 0), min(j + 1, days - 1)):
                            a, b = vals[k], vals[k + 1]
                            if a == 0.0:
                                hits.append(start + k)
                            elif (a < 0) != (b < 0) and abs(a - b) < 90:
                                hits.append(_bisect(f, start + k, start + k + 1, a))
                        hits = sorted(set(h for h in hits if w0 - 1 <= h <= w1 + 1))
                        if w1 >= jd0 and w0 <= jd1:  # episode intersects the period
                            base = {"transit": tp, "natal": nt, "type": typ, "type_ru": ru,
                                    "orb_max": orb_max, "window": [fmt.date(w0), fmt.date(w1)],
                                    "window_utc": [fmt.utc(w0), fmt.utc(w1)],
                                    "passes_total": len(hits),
                                    "importance": round(W_TRANSIT.get(tp, .3) * W_NATAL.get(nt, .3) * W_ASPECT[typ], 2)}
                            if hits:
                                for n, h in enumerate(hits, 1):
                                    speed = body_position(h, tp)[1]
                                    events.append(dict(base, date_exact=fmt.date(h), exact_utc=fmt.utc(h), exact=True,
                                                       retro_pass=n, transit_retrograde=speed < 0,
                                                       exact_in_period=jd0 <= h <= jd1))
                            else:
                                kmin = min(range(i, j + 1), key=lambda k: abs(vals[k]))
                                events.append(dict(base, date_exact=fmt.date(start + kmin), exact_utc=fmt.utc(start + kmin),
                                                   exact=False, retro_pass=0, min_orb=round(abs(vals[kmin]), 3),
                                                   transit_retrograde=body_position(start + kmin, tp)[1] < 0,
                                                   exact_in_period=jd0 <= start + kmin <= jd1))
                        i = j + 1
    events.sort(key=lambda e: (e["exact_utc"], -e["importance"]))
    return events


# ---------------------------------------------------------------- sky events
def _natal_house(lon: float, cusps: Optional[List[float]]) -> Optional[int]:
    return house_of(lon, cusps) if cusps else None


def stations(pid: str, jd0: float, jd1: float) -> List[Tuple[float, str]]:
    sp = lambda jd: body_position(jd, pid)[1]
    out = []
    prev = sp(jd0)
    jd = jd0
    while jd < jd1:
        nxt = sp(jd + 1)
        if (prev < 0) != (nxt < 0):
            t = _bisect(sp, jd, jd + 1, prev)
            out.append((t, "retrograde" if prev > 0 else "direct"))
        prev, jd = nxt, jd + 1
    return out


def retrogrades(pid: str, jd0: float, jd1: float, fmt: _Fmt, cusps) -> List[Dict]:
    st = stations(pid, jd0 - 200, jd1 + 200)
    res = []
    for k, (t, kind) in enumerate(st):
        if kind != "retrograde":
            continue
        end = next((t2 for t2, k2 in st[k + 1:] if k2 == "direct"), None)
        if end is None or end < jd0 or t > jd1:
            continue
        l0, l1 = body_position(t, pid)[0], body_position(end, pid)[0]
        res.append({"kind": f"{pid}_retrograde", "from": fmt.date(t), "to": fmt.date(end),
                    "from_utc": fmt.utc(t), "to_utc": fmt.utc(end),
                    "sign": C.SIGNS[sign_of(l0)], "sign_end": C.SIGNS[sign_of(l1)],
                    "station_retro_lon": round(l0, 4), "station_direct_lon": round(l1, 4),
                    "natal_house": _natal_house(l0, cusps)})
    return res


ECL_SOLAR = [(swe.ECL_TOTAL, "total"), (swe.ECL_ANNULAR, "annular"), (swe.ECL_ANNULAR_TOTAL, "hybrid"),
             (swe.ECL_PARTIAL, "partial")]
ECL_LUNAR = [(swe.ECL_TOTAL, "total"), (swe.ECL_PARTIAL, "partial"), (swe.ECL_PENUMBRAL, "penumbral")]


def eclipses(jd0: float, jd1: float, fmt: _Fmt, cusps) -> List[Dict]:
    res = []
    for kind, fn, types, body in (("solar_eclipse", swe.sol_eclipse_when_glob, ECL_SOLAR, "sun"),
                                  ("lunar_eclipse", swe.lun_eclipse_when, ECL_LUNAR, "moon")):
        jd = jd0
        while True:
            with LOCK:
                ret, tret = fn(jd, swe.FLG_SWIEPH, 0, False)
            t = tret[0]
            if t > jd1:
                break
            typ = next((n for flag, n in types if ret & flag), "unknown")
            lon = body_position(t, body)[0]
            res.append({"kind": kind, "date": fmt.date(t), "at_utc": fmt.utc(t), "eclipse_type": typ,
                        "sign": C.SIGNS[sign_of(lon)], "lon": round(lon, 4), "natal_house": _natal_house(lon, cusps)})
            jd = t + 20
    return res


def lunations(jd0: float, jd1: float, fmt: _Fmt, cusps) -> List[Dict]:
    def elong(jd):
        return norm360(body_position(jd, "moon")[0] - body_position(jd, "sun")[0])
    res = []
    jd = jd0
    prev = elong(jd)
    step = 0.25
    while jd < jd1:
        nxt = elong(jd + step)
        for target, kind in ((0.0, "new_moon"), (180.0, "full_moon")):
            a, b = angdiff(prev, target), angdiff(nxt, target)
            if a < 0 <= b and b - a < 90:
                t = _bisect(lambda x: angdiff(elong(x), target), jd, jd + step, a)
                lon = body_position(t, "moon")[0]
                res.append({"kind": kind, "date": fmt.date(t), "at_utc": fmt.utc(t), "sign": C.SIGNS[sign_of(lon)],
                            "lon": round(lon, 4), "natal_house": _natal_house(lon, cusps)})
        prev, jd = nxt, jd + step
    return res


def ingresses(planets: List[str], jd0: float, jd1: float, fmt: _Fmt, cusps) -> List[Dict]:
    res = []
    for pid in planets:
        jd = jd0
        prev = body_position(jd, pid)[0]
        while jd < jd1:
            nxt = body_position(jd + 1, pid)[0]
            s0, s1 = sign_of(prev), sign_of(nxt)
            if s0 != s1:
                # boundary between signs: the one crossed
                fwd = (s1 - s0) % 12 == 1
                boundary = (s1 * 30.0) if fwd else (s0 * 30.0)
                t = _bisect(lambda x: angdiff(body_position(x, pid)[0], boundary), jd, jd + 1,
                            angdiff(prev, boundary))
                res.append({"kind": "ingress", "planet": pid, "date": fmt.date(t), "at_utc": fmt.utc(t),
                            "sign": C.SIGNS[s1], "from_sign": C.SIGNS[s0], "retrograde": not fwd,
                            "natal_house": _natal_house(s1 * 30.0 + (0.0 if fwd else 29.999), cusps)})
            prev, jd = nxt, jd + 1
    return res


def transit_report(natal: Dict, date_from: str, date_to: str, *, tz: Optional[str] = None,
                   planets: Optional[List[str]] = None, targets: Optional[List[str]] = None,
                   orbs: Optional[Dict[str, float]] = None, sky: bool = True) -> Dict:
    tz = tz or natal["input"]["place"]["tz"]
    fmt = _Fmt(tz)
    z = get_zone(tz)
    d0 = dt.datetime.fromisoformat(date_from).replace(tzinfo=z)
    d1 = (dt.datetime.fromisoformat(date_to) + dt.timedelta(days=1)).replace(tzinfo=z)
    if d1 <= d0:
        raise ValueError("period.to must be after period.from")
    if (d1 - d0).days > 3 * 366 + 1:
        raise ValueError("period longer than 3 years")
    jd0, jd1 = julday_utc(d0), julday_utc(d1)
    planets = planets or TRANSIT_PLANETS_DEFAULT
    targets = targets or NATAL_TARGETS_DEFAULT
    o = dict(TRANSIT_ORB)
    o.update(orbs or {})
    cusps = house_cusps(natal)
    events = transit_events(natal, jd0, jd1, fmt, planets, targets, o)
    sky_events: List[Dict] = []
    if sky:
        for p in ("mercury", "venus", "mars"):
            sky_events += retrogrades(p, jd0, jd1, fmt, cusps)
        sky_events += eclipses(jd0, jd1, fmt, cusps)
        sky_events += lunations(jd0, jd1, fmt, cusps)
        sky_events += ingresses(["sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"],
                                jd0, jd1, fmt, cusps)
        sky_events.sort(key=lambda e: e.get("at_utc") or e.get("from_utc"))
    return {"schema": "transits/0.1", "natal_ref": natal["chart_id"],
            "period": {"from": date_from, "to": date_to}, "tz": tz,
            "settings": {"transit_planets": planets, "natal_targets": targets, "orbs": {p: o[p] for p in planets}},
            "events": events, "sky_events": sky_events}
