"""Offline city search over a compact GeoNames extract (Russian-first).

Data: GeoNames (https://www.geonames.org/), licence CC BY 4.0 — attribution required
("Geographical data © GeoNames, CC BY 4.0"). Built by scripts/build_geo.py from
cities5000 (worldwide) + cities1000 (former USSR) + Russian alternate names.

Search: normalised prefix/substring match on Russian names (current and historic, e.g.
"Куйбышев" -> Samara, "Свердловск" -> Yekaterinburg), English/ASCII names and other
Cyrillic spellings; ranked by match quality then population.
"""
from __future__ import annotations

import csv
import functools
import gzip
import os
import re
from typing import Dict, List, Optional

DATA_PATH = os.environ.get("ASTRO_GEO_DATA",
                           os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cities_ru.tsv.gz"))
ATTRIBUTION = "Geographical data © GeoNames (geonames.org), CC BY 4.0"

_ws = re.compile(r"[\s\-‐–—'’`\.,()]+")


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е").replace("й", "и")
    return _ws.sub(" ", s).strip()


class _Index:
    def __init__(self, path: str):
        self.rows: List[Dict] = []
        self.by_id: Dict[int, Dict] = {}
        self.keys: List[tuple] = []  # (normalised key, row index, kind)
        csv.field_size_limit(10_000_000)
        with gzip.open(path, "rt", encoding="utf-8") as f:
            r = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar="\\")
            header = next(r)
            for p in r:
                row = dict(zip(header, p))
                rec = {
                    "geoname_id": int(row["geoname_id"]),
                    "name": row["name"],
                    "name_ru": row["name_ru"] or row["name"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "country": row["country"],
                    "country_ru": row["country_ru"],
                    "admin1_ru": row["admin1_ru"],
                    "population": int(row["population"] or 0),
                    "tz": row["tz"],
                    "historic_names_ru": [x for x in row["alt_hist_ru"].split("|") if x],
                }
                i = len(self.rows)
                self.rows.append(rec)
                self.by_id[rec["geoname_id"]] = rec
                seen = set()
                for kind, names in (("ru", [rec["name_ru"]] + row["alt_ru"].split("|")),
                                    ("hist", row["alt_hist_ru"].split("|")),
                                    ("en", [rec["name"]]),
                                    ("other", row["alt_other"].split("|"))):
                    for n in names:
                        k = norm(n)
                        if k and k not in seen:
                            seen.add(k)
                            self.keys.append((k, i, kind))
        self.keys.sort()


@functools.lru_cache(maxsize=1)
def _index() -> _Index:
    return _Index(DATA_PATH)


def _clean(s: str) -> str:
    s = s.replace("\u0301", "")
    for a, b in ((" Область", " область"), (" Край", " край"), (" Республика", " республика"),
                 (" Автономный Округ", " автономный округ")):
        s = s.replace(a, b)
    return s


def _label(rec: Dict) -> str:
    parts = [rec["name_ru"]]
    if rec["admin1_ru"] and rec["admin1_ru"] != rec["name_ru"]:
        parts.append(rec["admin1_ru"])
    if rec["country_ru"]:
        parts.append(rec["country_ru"])
    return _clean(", ".join(parts))


def search(q: str, limit: int = 10, country: Optional[str] = None) -> List[Dict]:
    """Search cities. Returns list of place dicts compatible with BirthInput.place."""
    import bisect
    idx = _index()
    nq = norm(q)
    if len(nq) < 2:
        return []
    # optional ", region" part: "Березовский, Свердловская" -> filter by admin/country text
    qualifier = None
    if "," in q:
        head, _, tail = q.partition(",")
        nq, qualifier = norm(head), norm(tail)
    best: Dict[int, tuple] = {}
    lo = bisect.bisect_left(idx.keys, (nq,))
    for j in range(lo, len(idx.keys)):
        k, i, kind = idx.keys[j]
        if not k.startswith(nq):
            break
        exact = k == nq
        score = (0 if exact else 1, {"ru": 0, "hist": 1, "en": 1, "other": 2}[kind])
        if i not in best or score < best[i][0]:
            best[i] = (score, kind)
    out = []
    for i, (score, kind) in best.items():
        rec = idx.rows[i]
        if country and rec["country"] != country.upper():
            continue
        if qualifier and qualifier not in norm(rec["admin1_ru"]) and qualifier not in norm(rec["country_ru"]):
            continue
        weight = {"ru": 1.0, "en": 1.0, "hist": 0.3, "other": 0.2}[kind]
        out.append((score[0], -rec["population"] * weight, score[1], i, kind))
    out.sort()
    res = []
    for _, _, _, i, kind in out[:limit]:
        rec = idx.rows[i]
        res.append({
            "geoname_id": rec["geoname_id"], "name_ru": rec["name_ru"], "label": _label(rec),
            "lat": rec["lat"], "lon": rec["lon"], "country": rec["country"], "tz": rec["tz"],
            "population": rec["population"], "matched_historic_name": kind == "hist",
            "historic_names_ru": rec["historic_names_ru"],
        })
    return res


def get(geoname_id: int) -> Optional[Dict]:
    rec = _index().by_id.get(int(geoname_id))
    if not rec:
        return None
    return {"geoname_id": rec["geoname_id"], "name_ru": rec["name_ru"], "label": _label(rec), "lat": rec["lat"],
            "lon": rec["lon"], "country": rec["country"], "tz": rec["tz"], "population": rec["population"]}


@functools.lru_cache(maxsize=1)
def _tf():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


def tz_for(lat: float, lon: float) -> Optional[str]:
    """IANA zone for coordinates (timezonefinder, offline polygons from timezone-boundary-builder)."""
    return _tf().timezone_at(lat=lat, lng=lon)
