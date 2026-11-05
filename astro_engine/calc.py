"""Natal chart calculation on Swiss Ephemeris (pyswisseph), output = docs/CHART_SCHEMA.md `NatalChart`.

Conventions (see docs/ENGINE.md):
* tropical zodiac, geocentric, apparent positions (light-time, aberration, nutation) — the
  Swiss Ephemeris defaults, identical to astro.com;
* time scale: UT input, Delta-T by Swiss Ephemeris;
* true node, mean Lilith (mean lunar apogee), Chiron from seas_18.se1;
* houses: Placidus default, Koch / Porphyry / Whole sign optional; Placidus & Koch are undefined
  inside the polar circles (|lat| > 90° - obliquity ≈ 66.56°) — automatic fallback to Porphyry
  with warning `house_system_fallback`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import json
import os
import threading
from typing import Dict, List, Optional, Tuple

import swisseph as swe

from . import __version__
from . import constants as C
from . import geo
from .timezones import TZ_SOURCE, TimezoneError, confirm_text_ru, local_to_utc, get_zone

EPHE_PATH = os.environ.get("ASTRO_EPHE_PATH",
                           os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ephe"))
# Путь у Swiss Ephemeris хранится отдельно в каждом потоке (TLS), а сервер считает в пуле потоков:
# set_ephe_path из главного потока до них не доходит, и они молча уходят на Moshier. Переменную
# окружения SE_EPHE_PATH библиотека читает в любом потоке при первом расчёте.
os.environ["SE_EPHE_PATH"] = EPHE_PATH
swe.set_ephe_path(EPHE_PATH)
LOCK = threading.RLock()

SWE_ID = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS, "mars": swe.MARS,
    "jupiter": swe.JUPITER, "saturn": swe.SATURN, "uranus": swe.URANUS, "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO, "true_node": swe.TRUE_NODE, "chiron": swe.CHIRON, "lilith": swe.MEAN_APOG,
}
BODY_POINTS = C.PLANETS + C.EXTRA_POINTS
HOUSE_SYSTEMS = {"P": "placidus", "K": "koch", "O": "porphyry", "W": "whole_sign"}
FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED


class InputError(ValueError):
    pass


# ---------------------------------------------------------------- helpers
def norm360(x: float) -> float:
    x = x % 360.0
    return 0.0 if abs(x - 360.0) < 1e-12 else x


def angdiff(a: float, b: float) -> float:
    """Signed smallest difference a-b in (-180, 180]."""
    d = (a - b) % 360.0
    return d - 360.0 if d > 180.0 else d


def sign_of(lon: float) -> int:
    return int(norm360(lon) // 30) % 12


def dms(lon_in_sign: float) -> str:
    # truncate (never round up to 30°00′ inside the same sign)
    total = int(math.floor(lon_in_sign * 3600 + 1e-7))
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}′{s:02d}″"


def ephemeris_label(retflag: int) -> str:
    if retflag & swe.FLG_SWIEPH:
        return f"Swiss Ephemeris {swe.version} (SE files)"
    if retflag & swe.FLG_MOSEPH:
        return f"Swiss Ephemeris {swe.version} (Moshier fallback)"
    return f"Swiss Ephemeris {swe.version}"


def julday_utc(t: dt.datetime) -> float:
    t = t.astimezone(dt.timezone.utc)
    h = t.hour + t.minute / 60 + (t.second + t.microsecond / 1e6) / 3600
    return swe.julday(t.year, t.month, t.day, h, swe.GREG_CAL)


def body_position(jd_ut: float, pid: str) -> Tuple[float, float, int]:
    """Return (longitude, speed deg/day, retflag)."""
    with LOCK:
        xx, ret = swe.calc_ut(jd_ut, SWE_ID[pid], FLAGS)
    return norm360(xx[0]), xx[3], ret


def obliquity(jd_ut: float) -> float:
    with LOCK:
        xx, _ = swe.calc_ut(jd_ut, swe.ECL_NUT, 0)
    return xx[0]


def compute_houses(jd_ut: float, lat: float, lon: float, hsys: str) -> Tuple[List[float], float, float, str, List[str]]:
    """Return cusps(12), asc, mc, system_used, warnings."""
    warnings = []
    used = hsys
    with LOCK:
        if hsys in ("P", "K") and abs(lat) >= 90.0 - obliquity(jd_ut) - 1e-9:
            used = "O"
            warnings.append("house_system_fallback")
        try:
            cusps, ascmc = swe.houses_ex(jd_ut, lat, lon, used.encode())
        except swe.Error:
            used = "O"
            if "house_system_fallback" not in warnings:
                warnings.append("house_system_fallback")
            cusps, ascmc = swe.houses_ex(jd_ut, lat, lon, b"O")
    cusps = [norm360(c) for c in cusps[:12]]
    return cusps, norm360(ascmc[0]), norm360(ascmc[1]), used, warnings


def house_of(lon: float, cusps: List[float]) -> int:
    for i in range(12):
        a, b = cusps[i], cusps[(i + 1) % 12]
        width = (b - a) % 360.0
        if (lon - a) % 360.0 < width or width == 0 and abs(angdiff(lon, a)) < 1e-9:
            return i + 1
    return 12  # numerical edge


def dignity(pid: str, sign: str) -> Optional[str]:
    if pid in C.DOMICILE and sign in C.DOMICILE[pid]:
        return "domicile"
    if C.EXALTATION.get(pid) == sign:
        return "exaltation"
    if pid in C.DETRIMENT and sign in C.DETRIMENT[pid]:
        return "detriment"
    if C.FALL.get(pid) == sign:
        return "fall"
    return None


# ---------------------------------------------------------------- input
def resolve_place(place: Dict, warnings: List[str]) -> Dict:
    if not isinstance(place, dict):
        raise InputError("place must be an object")
    p = dict(place)
    if p.get("lat") is None or p.get("lon") is None:
        rec = None
        if p.get("geoname_id"):
            rec = geo.get(p["geoname_id"])
        elif p.get("query"):
            hits = geo.search(p["query"], limit=1)
            rec = hits[0] if hits else None
            if rec:
                warnings.append("place_auto_resolved")
        if not rec:
            raise InputError("place not found: provide lat/lon, geoname_id or a known query")
        p.setdefault("geoname_id", rec["geoname_id"])
        p["lat"], p["lon"] = rec["lat"], rec["lon"]
        p.setdefault("country", rec["country"])
        if not p.get("tz"):
            p["tz"] = rec["tz"]
    lat, lon = float(p["lat"]), float(p["lon"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InputError("lat/lon out of range")
    p["lat"], p["lon"] = lat, lon
    if not p.get("tz"):
        tz = geo.tz_for(lat, lon)
        if not tz:
            raise InputError("cannot determine time zone for coordinates; pass place.tz")
        p["tz"] = tz
        warnings.append("tz_from_coordinates")
    return p


def parse_birth_input(inp: Dict) -> Dict:
    if not isinstance(inp, dict):
        raise InputError("BirthInput must be an object")
    out = dict(inp)
    if "date" not in out:
        raise InputError("date is required (YYYY-MM-DD)")
    tk = out.get("time_known")
    if tk is None:
        tk = out.get("time") not in (None, "")
    out["time_known"] = bool(tk)
    if not out["time_known"]:
        out["time"] = None
    elif not out.get("time"):
        raise InputError("time is required when time_known=true")
    hs = (out.get("house_system") or "P").upper()
    if hs not in HOUSE_SYSTEMS:
        raise InputError(f"house_system must be one of {sorted(HOUSE_SYSTEMS)}")
    out["house_system"] = hs
    if "place" not in out:
        raise InputError("place is required")
    return out


# ---------------------------------------------------------------- aspects
def find_aspects(pos: Dict[str, Dict], ids: List[str], factor: float = 1.0) -> List[Dict]:
    res = []
    dtd = 1.0 / 1440.0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if {a, b} == {"asc", "mc"}:
                continue
            la, lb = pos[a]["lon"], pos[b]["lon"]
            sep = abs(angdiff(la, lb))
            for typ, ang, ru in C.ASPECTS:
                orb_max = C.pair_orb(a, b, typ, factor)
                orb = abs(sep - ang)
                if orb <= orb_max:
                    la2 = la + pos[a].get("speed", 0.0) * dtd
                    lb2 = lb + pos[b].get("speed", 0.0) * dtd
                    orb2 = abs(abs(angdiff(la2, lb2)) - ang)
                    res.append({"a": a, "b": b, "type": typ, "type_ru": ru, "angle": ang,
                                "orb": round(orb, 2), "orb_exact": round(orb, 6),
                                "applying": bool(orb2 < orb), "orb_max": orb_max})
                    break
    res.sort(key=lambda x: x["orb_exact"])
    return res


# ---------------------------------------------------------------- aspect patterns
def find_patterns(aspects: List[Dict]) -> List[Dict]:
    """Classical configurations among the ten planets: grand trine, T-square, grand cross (docs/READING_RULES.md §2)."""
    rel: Dict[frozenset, str] = {}
    for a in aspects:
        if a["a"] in C.PLANETS and a["b"] in C.PLANETS:
            rel[frozenset((a["a"], a["b"]))] = a["type"]
    has = lambda x, y, t: rel.get(frozenset((x, y))) == t  # noqa: E731
    order = C.PLANETS.index
    out: List[Dict] = []
    ps = C.PLANETS
    for i, x in enumerate(ps):
        for j in range(i + 1, len(ps)):
            y = ps[j]
            if has(x, y, "opposition"):
                for z in ps:
                    if z not in (x, y) and has(x, z, "square") and has(y, z, "square"):
                        out.append({"type": "t_square", "points": [x, y, z], "apex": z})
            for k in range(j + 1, len(ps)):
                z = ps[k]
                if has(x, y, "trine") and has(y, z, "trine") and has(x, z, "trine"):
                    out.append({"type": "grand_trine", "points": [x, y, z]})
    crosses = set()
    for t in [p for p in out if p["type"] == "t_square"]:
        x, y, z = t["points"]
        for w in ps:
            if w not in (x, y, z) and has(z, w, "opposition") and has(x, w, "square") and has(y, w, "square"):
                crosses.add(tuple(sorted((x, y, z, w), key=order)))
    out += [{"type": "grand_cross", "points": list(c)} for c in sorted(crosses)]
    return out


# ---------------------------------------------------------------- summary
def build_summary(points: Dict[str, Dict], aspects: List[Dict], time_known: bool, angles: Optional[Dict]) -> Dict:
    elements = {"fire": 0, "earth": 0, "air": 0, "water": 0}
    modalities = {"cardinal": 0, "fixed": 0, "mutable": 0}
    by_sign: Dict[str, List[str]] = {}
    by_house: Dict[int, List[str]] = {}
    for pid in C.PLANETS:
        s = points[pid]["sign"]
        elements[C.SIGN_ELEMENT[s]] += 1
        modalities[C.SIGN_MODALITY[s]] += 1
        by_sign.setdefault(s, []).append(pid)
        if points[pid].get("house"):
            by_house.setdefault(points[pid]["house"], []).append(pid)
    stelliums = [{"sign": s, "points": ps} for s, ps in by_sign.items() if len(ps) >= 3]
    house_stelliums = [{"house": h, "points": ps} for h, ps in sorted(by_house.items()) if len(ps) >= 3]

    # dominant planets: transparent additive score (documented in docs/ENGINE.md)
    score = {p: 0.0 for p in C.PLANETS}
    if time_known and angles:
        score[C.TRAD_RULER[points["asc"]["sign"]]] += 3
        score[C.TRAD_RULER[points["mc"]["sign"]]] += 1
        for p in C.PLANETS:
            for ang in ("asc", "mc", "dsc", "ic"):
                if abs(angdiff(points[p]["lon"], angles[ang])) <= 6:
                    score[p] += 3
                    break
            if points[p].get("house") in (1, 4, 7, 10):
                score[p] += 1
    score[C.TRAD_RULER[points["sun"]["sign"]]] += 1
    score[C.TRAD_RULER[points["moon"]["sign"]]] += 1
    for p in C.PLANETS:
        d = points[p]["dignity"]
        score[p] += {"domicile": 2, "exaltation": 1}.get(d, 0)
    for st in stelliums:
        score[C.TRAD_RULER[st["sign"]]] += 1
    for a in aspects:
        for p in (a["a"], a["b"]):
            if p in score:
                score[p] += 1.0 if a["orb_exact"] <= 3 else 0.5
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], C.PLANETS.index(kv[0])))
    dominant = [p for p, s in ranked[:2]]
    return {
        "elements": elements, "modalities": modalities,
        "big_three": {"sun": points["sun"]["sign"], "moon": points["moon"]["sign"],
                      "asc": points["asc"]["sign"] if time_known and "asc" in points else None},
        "dominant_planets": dominant,
        "dominant_scores": {p: round(s, 2) for p, s in ranked},
        "stelliums": stelliums,
        "house_stelliums": house_stelliums,
        "patterns": find_patterns(aspects),
    }


# ---------------------------------------------------------------- main entry
def natal_chart(inp: Dict, *, fold: Optional[int] = None) -> Dict:
    birth = parse_birth_input(inp)
    warnings: List[str] = []
    place = resolve_place(birth["place"], warnings)
    birth["place"] = place
    try:
        tzr = local_to_utc(birth["date"], birth["time"], place["tz"], fold=fold if fold is not None else birth.get("fold"),
                           lon=place["lon"])
    except TimezoneError as e:
        raise InputError(str(e))
    time_warnings = list(tzr["time_warnings"])
    # cross-check the zone against coordinates (offset at birth time must agree)
    try:
        tz_coord = geo.tz_for(place["lat"], place["lon"])
    except Exception:
        tz_coord = None
    tz_check = None
    if tz_coord and tz_coord != place["tz"]:
        try:
            alt = local_to_utc(birth["date"], birth["time"], tz_coord)
            if abs(alt["utc_offset_hours"] - tzr["utc_offset_hours"]) > 1e-6:
                time_warnings.append("tz_place_mismatch")
                tz_check = {"tz_by_coordinates": tz_coord, "utc_offset_hours": alt["utc_offset_hours"]}
        except TimezoneError:
            pass
    ovr = birth.get("utc_offset_override")
    if ovr is not None:
        # user-confirmed offset (UX: "в 1989 в Самаре было UTC+4, верно?" -> "нет, UTC+3")
        try:
            ovr = float(ovr)
        except (TypeError, ValueError):
            raise InputError("utc_offset_override must be a number of hours")
        if not -14 <= ovr <= 14:
            raise InputError("utc_offset_override out of range")
        hh, mm = (birth["time"] or "12:00").split(":")[:2]
        naive = dt.datetime.fromisoformat(f"{birth['date']}T{int(hh):02d}:{int(mm):02d}")
        tzr["utc"] = (naive - dt.timedelta(hours=ovr)).replace(tzinfo=dt.timezone.utc)
        tzr["tz_details"]["tzdb_utc_offset_hours"] = tzr["utc_offset_hours"]
        tzr["utc_offset_hours"] = ovr
        time_warnings.append("utc_offset_user_override")
    utc = tzr["utc"]
    label = place.get("label") or place.get("query") or place["tz"]
    tzr["tz_details"]["confirm_ru"] = confirm_text_ru(birth["date"], label, tzr["utc_offset_hours"], time_warnings)
    jd = julday_utc(utc)
    time_known = birth["time_known"]

    pos: Dict[str, Dict] = {}
    eph_flags = 0
    for pid in BODY_POINTS:
        try:
            lon, speed, ret = body_position(jd, pid)
        except swe.Error:
            warnings.append(f"{pid}_unavailable")
            continue
        if pid in C.PLANETS:
            eph_flags |= ret
        pos[pid] = {"lon": lon, "speed": speed}
    houses_out: List[Dict] = []
    angles = None
    used_hs = birth["house_system"]
    cusps = None
    if time_known:
        cusps, asc, mc, used_hs, hw = compute_houses(jd, place["lat"], place["lon"], birth["house_system"])
        warnings += hw
        _, asc2, mc2, _, _ = compute_houses(jd + 1 / 1440, place["lat"], place["lon"], "O")
        _, asc1, mc1, _, _ = compute_houses(jd - 1 / 1440, place["lat"], place["lon"], "O")
        pos["asc"] = {"lon": asc, "speed": angdiff(asc2, asc1) / (2 / 1440)}
        pos["mc"] = {"lon": mc, "speed": angdiff(mc2, mc1) / (2 / 1440)}
        angles = {"asc": round(asc, 6), "mc": round(mc, 6), "dsc": round(norm360(asc + 180), 6),
                  "ic": round(norm360(mc + 180), 6)}
        houses_out = [{"n": i + 1, "cusp_lon": round(c, 6), "sign": C.SIGNS[sign_of(c)],
                       "sign_ru": C.SIGNS_RU[sign_of(c)], "deg_in_sign": round(c % 30, 6)} for i, c in enumerate(cusps)]

    # sign ranges for unknown time: positions at 00:00 and 23:59:59 local
    ranges: Dict[str, List[str]] = {}
    if not time_known:
        lo = local_to_utc(birth["date"], "00:00", place["tz"])["utc"]
        hi = local_to_utc(birth["date"], "23:59:59", place["tz"])["utc"]
        for pid in pos:
            s0 = sign_of(body_position(julday_utc(lo), pid)[0])
            s1 = sign_of(body_position(julday_utc(hi), pid)[0])
            if s0 != s1:
                ranges[pid] = [C.SIGNS[s0], C.SIGNS[s1]]

    points: Dict[str, Dict] = {}
    order = [p for p in C.ALL_POINTS if p in pos]
    for pid in order:
        lon = pos[pid]["lon"]
        si = sign_of(lon)
        rec = {"id": pid, "name_ru": C.POINT_RU[pid], "lon": round(lon, 6), "sign": C.SIGNS[si],
               "sign_ru": C.SIGNS_RU[si], "deg_in_sign": round(lon - si * 30, 6), "dms": dms(lon - si * 30),
               "house": house_of(lon, cusps) if cusps else None,
               "retrograde": bool(pid not in ("asc", "mc") and pos[pid]["speed"] < 0),
               "speed": round(pos[pid]["speed"], 6),
               "dignity": dignity(pid, C.SIGNS[si]) if pid in C.PLANETS else None}
        if pid in ("asc", "mc"):
            rec["speed"] = round(pos[pid]["speed"], 3)
        if pid in C.PLANETS and pid not in ("sun", "moon") and abs(pos[pid]["speed"]) < 0.05 * _mean_speed(pid):
            rec["stationary"] = True
        if pid in ranges:
            rec["sign_range"] = ranges[pid]
        points[pid] = rec

    aspect_ids = [p for p in order]
    aspects = find_aspects(pos, aspect_ids)
    if not time_known:
        for a in aspects:
            if "moon" in (a["a"], a["b"]):
                a["uncertain"] = True
    summary = build_summary(points, aspects, time_known, angles)
    if "moon" in ranges:
        summary["moon_sign_range"] = ranges["moon"]

    chart = {
        "schema": "natal/0.1",
        "input": birth,
        "utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "utc_offset_hours": tzr["utc_offset_hours"],
        "tz_source": TZ_SOURCE,
        "time_warnings": time_warnings,
        "julian_day_ut": round(jd, 8),
        "points": [points[p] for p in order],
        "houses": houses_out,
        "angles": angles,
        "aspects": aspects,
        "summary": summary,
        "engine": {"name": "astro-engine", "version": __version__, "ephemeris": ephemeris_label(eph_flags),
                   "house_system_requested": birth["house_system"], "house_system_used": used_hs if time_known else None,
                   "zodiac": "tropical", "node": "true", "lilith": "mean"},
        "warnings": warnings,
        "tz_details": dict(tzr["tz_details"], **({"coordinate_check": tz_check} if tz_check else {})),
    }
    if tzr["alternatives"]:
        chart["tz_alternatives"] = tzr["alternatives"]
    chart["chart_id"] = chart_hash(chart)
    return chart


_MEAN_SPEED = {"sun": 0.9856, "moon": 13.18, "mercury": 1.38, "venus": 1.2, "mars": 0.524, "jupiter": 0.083,
               "saturn": 0.0335, "uranus": 0.0117, "neptune": 0.006, "pluto": 0.004}


def _mean_speed(pid: str) -> float:
    return _MEAN_SPEED.get(pid, 1.0)


def chart_hash(chart: Dict) -> str:
    key = {"utc": chart["utc"], "lat": chart["input"]["place"]["lat"], "lon": chart["input"]["place"]["lon"],
           "time_known": chart["input"]["time_known"], "hs": chart["input"]["house_system"]}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def point_map(chart: Dict) -> Dict[str, Dict]:
    return {p["id"]: p for p in chart["points"]}


def house_cusps(chart: Dict) -> Optional[List[float]]:
    return [h["cusp_lon"] for h in chart["houses"]] if chart["houses"] else None
