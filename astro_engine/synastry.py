"""Synastry: inter-chart aspects + house overlays. Output = `SynastryReport` (docs/CHART_SCHEMA.md)."""
from __future__ import annotations

from typing import Dict, List

from . import constants as C
from .calc import angdiff, house_of, house_cusps, natal_chart, point_map

SYN_POINTS = C.PLANETS + ["true_node", "chiron", "lilith", "asc", "mc"]


def inter_aspects(c1: Dict, c2: Dict, factor: float = C.SYNASTRY_ORB_FACTOR) -> List[Dict]:
    p1, p2 = point_map(c1), point_map(c2)
    out = []
    for a in SYN_POINTS:
        if a not in p1:
            continue
        for b in SYN_POINTS:
            if b not in p2:
                continue
            if a in ("asc", "mc") and b in ("asc", "mc") and a != b:
                continue
            sep = abs(angdiff(p1[a]["lon"], p2[b]["lon"]))
            for typ, ang, ru in C.ASPECTS:
                orb_max = C.pair_orb(a, b, typ, factor)
                orb = abs(sep - ang)
                if orb <= orb_max:
                    rec = {"a_person": 1, "a": a, "b_person": 2, "b": b, "type": typ, "type_ru": ru,
                           "angle": ang, "orb": round(orb, 2), "orb_max": round(orb_max, 2)}
                    unc = [n for n, c, pid in ((1, c1, a), (2, c2, b))
                           if pid == "moon" and not c["input"]["time_known"]]
                    if unc:
                        rec["uncertain"] = True
                    out.append(rec)
                    break
    out.sort(key=lambda x: x["orb"])
    return out


def overlays(src: Dict, dst: Dict, src_n: int, dst_n: int) -> List[Dict]:
    cusps = house_cusps(dst)
    if not cusps:
        return []
    return [{"person": src_n, "point": p["id"], "in_houses_of": dst_n, "house": house_of(p["lon"], cusps)}
            for p in src["points"] if p["id"] in C.PLANETS + ["true_node", "chiron", "lilith"]]


def synastry_report(in1: Dict, in2: Dict) -> Dict:
    c1, c2 = natal_chart(in1), natal_chart(in2)
    both = c1["input"]["time_known"] and c2["input"]["time_known"]
    return {
        "schema": "synastry/0.1",
        "charts": [c1, c2],
        "aspects": inter_aspects(c1, c2),
        "house_overlays": (overlays(c1, c2, 1, 2) + overlays(c2, c1, 2, 1)) if both else [],
        "settings": {"orb_factor": C.SYNASTRY_ORB_FACTOR,
                     "house_overlays_rule": "only when both birth times are known (CHART_SCHEMA v0.1)"},
    }
