"""Local civil time -> UTC using the IANA tz database (historical rules).

Design decisions
----------------
* tz data comes ONLY from the pinned PyPI ``tzdata`` package (not from the OS), so a
  macOS laptop and a Linux VPS give identical answers. Version is reported in
  ``tz_source`` (e.g. "tzdb 2026e").
* Ambiguous local times (clock set back, the same wall time happens twice) and
  non-existent ones (clock set forward, wall time skipped) are detected explicitly
  and reported as ``dst_ambiguous`` / ``dst_nonexistent`` with both candidate
  offsets, so the UI can ask the user.
* Former-USSR zones get extra flags (see TIMEZONES.md):
    - ``ussr_pre_1970_low_confidence`` - tzdb itself warns USSR data before 1970 is unreliable;
    - ``ussr_1991_transition``          - 1991-03-01 .. 1992-03-31, decree time abolished/returned;
    - ``tz_regime_change``              - the zone changed its *standard* offset within
                                         +-1 year of the birth (Samara 1989, Volgograd 2018 ...);
    - ``tz_zone_merged``                - the zone is a backward link (e.g. Europe/Zaporozhye ->
                                         Europe/Kyiv) whose own history was lost.
"""
from __future__ import annotations

import datetime as dt
import functools
import importlib.resources as resources
import zoneinfo
from typing import Dict, List, Optional

try:
    import tzdata  # pinned IANA data
    TZDB_VERSION = getattr(tzdata, "IANA_VERSION", "unknown")
except Exception:  # pragma: no cover
    tzdata = None
    TZDB_VERSION = "system"

TZ_SOURCE = f"tzdb {TZDB_VERSION}"

UTC = dt.timezone.utc

# Zones of the former USSR (tzdb canonical names + common links).
EX_USSR_ZONES = {
    "Europe/Moscow", "Europe/Simferopol", "Europe/Kaliningrad", "Europe/Samara", "Europe/Volgograd",
    "Europe/Saratov", "Europe/Ulyanovsk", "Europe/Astrakhan", "Europe/Kirov", "Europe/Kyiv", "Europe/Kiev",
    "Europe/Uzhgorod", "Europe/Zaporozhye", "Europe/Minsk", "Europe/Riga", "Europe/Vilnius", "Europe/Tallinn",
    "Europe/Chisinau", "Europe/Tiraspol",
    "Asia/Yekaterinburg", "Asia/Omsk", "Asia/Novosibirsk", "Asia/Barnaul", "Asia/Tomsk", "Asia/Novokuznetsk",
    "Asia/Krasnoyarsk", "Asia/Irkutsk", "Asia/Chita", "Asia/Yakutsk", "Asia/Khandyga", "Asia/Vladivostok",
    "Asia/Ust-Nera", "Asia/Magadan", "Asia/Sakhalin", "Asia/Srednekolymsk", "Asia/Kamchatka", "Asia/Anadyr",
    "Asia/Almaty", "Asia/Qostanay", "Asia/Qyzylorda", "Asia/Aqtobe", "Asia/Aqtau", "Asia/Atyrau", "Asia/Oral",
    "Asia/Tashkent", "Asia/Samarkand", "Asia/Bishkek", "Asia/Dushanbe", "Asia/Ashgabat", "Asia/Baku",
    "Asia/Tbilisi", "Asia/Yerevan",
}

# Backward links whose separate pre-merge history is not in the main tzdb data.
MERGED_LINKS = {
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Tiraspol": "Europe/Chisinau",
}


class TimezoneError(ValueError):
    pass


@functools.lru_cache(maxsize=512)
def get_zone(name: str) -> zoneinfo.ZoneInfo:
    """Load a zone from the pinned tzdata package (falls back to system tz only if tzdata is absent)."""
    if not name or ".." in name or name.startswith("/"):
        raise TimezoneError(f"bad tz name: {name!r}")
    if tzdata is not None:
        try:
            res = resources.files("tzdata.zoneinfo").joinpath(*name.split("/"))
            with res.open("rb") as f:
                return zoneinfo.ZoneInfo.from_file(f, key=name)
        except (FileNotFoundError, IsADirectoryError, OSError):
            raise TimezoneError(f"unknown IANA time zone: {name!r}")
    try:  # pragma: no cover
        return zoneinfo.ZoneInfo(name)
    except Exception as e:  # pragma: no cover
        raise TimezoneError(f"unknown IANA time zone: {name!r}") from e


def _offset_h(td: Optional[dt.timedelta]) -> float:
    return round(td.total_seconds() / 3600.0, 6) if td is not None else 0.0


def _std_offset(z, when: dt.datetime) -> float:
    loc = when.astimezone(z)
    return _offset_h(loc.utcoffset() - (loc.dst() or dt.timedelta(0)))


def _regime_change_near(z, local: dt.datetime) -> Optional[Dict]:
    """Return info if the zone's standard (non-DST) offset changed within +-400 days of the date."""
    base = dt.datetime(local.year, local.month, local.day, 12, tzinfo=UTC)
    samples = [base + dt.timedelta(days=d) for d in range(-400, 401, 15)]
    stds = [_std_offset(z, s) for s in samples]
    changes = []
    for i in range(1, len(stds)):
        if abs(stds[i] - stds[i - 1]) > 1e-6:
            changes.append({"around": samples[i].date().isoformat(), "from_std": stds[i - 1], "to_std": stds[i]})
    # also detect a change of total offset pattern not explained by DST (e.g. "permanent DST" 2011)
    return {"changes": changes} if changes else None


def local_to_utc(date: str, time: Optional[str], tz_name: str, *, fold: Optional[int] = None,
                 lon: Optional[float] = None) -> Dict:
    """Convert local civil date/time in an IANA zone to UTC.

    ``fold``: when the user has already disambiguated an ambiguous time pass 0 (first
    occurrence, before clocks went back) or 1 (second occurrence).
    Returns dict: utc (aware datetime), utc_offset_hours, time_warnings (list[str]),
    tz_details (machine-readable explanation for UI), alternatives (list for ambiguous/nonexistent).
    """
    z = get_zone(tz_name)
    try:
        d = dt.date.fromisoformat(date)
    except Exception as e:
        raise TimezoneError(f"bad date: {date!r}") from e
    warnings: List[str] = []
    details: Dict = {"tz": tz_name, "tzdb": TZDB_VERSION}
    if time is None:
        hh, mm, ss = 12, 0, 0
        warnings.append("time_unknown")
    else:
        try:
            parts = [int(x) for x in time.split(":")]
            hh, mm = parts[0], parts[1]
            ss = parts[2] if len(parts) > 2 else 0
            dt.time(hh, mm, ss)
        except Exception as e:
            raise TimezoneError(f"bad time: {time!r}") from e
    naive = dt.datetime(d.year, d.month, d.day, hh, mm, ss)
    a0 = naive.replace(tzinfo=z, fold=0)
    a1 = naive.replace(tzinfo=z, fold=1)
    o0, o1 = a0.utcoffset(), a1.utcoffset()
    alternatives = []
    chosen = a0
    if o0 != o1:
        # Either ambiguous (fall back) or non-existent (spring forward).
        rt0 = a0.astimezone(UTC).astimezone(z).replace(tzinfo=None)
        rt1 = a1.astimezone(UTC).astimezone(z).replace(tzinfo=None)
        exists = (rt0 == naive) or (rt1 == naive)
        for a in (a0, a1):
            alternatives.append({"fold": a.fold, "utc_offset_hours": _offset_h(a.utcoffset()),
                                 "utc": a.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})
        if exists:
            warnings.append("dst_ambiguous")
            chosen = a1 if fold == 1 else a0
        else:
            warnings.append("dst_nonexistent")
            # Wall time was skipped: most likely the clock had not yet been moved
            # (or the record uses the old offset). Use the pre-transition offset (fold=0,
            # PEP 495), and offer the other one.
            chosen = a1 if fold == 1 else a0
    utc = chosen.astimezone(UTC)
    off = _offset_h(chosen.utcoffset())
    details.update({"utc_offset_hours": off, "dst": _offset_h(chosen.dst()) != 0.0, "abbr": chosen.tzname()})
    non_quarter = abs(off * 4 - round(off * 4)) > 1e-6
    if chosen.tzname() == "LMT" or (non_quarter and tz_name in EX_USSR_ZONES):
        # Before standard time: tzdb's LMT is the mean time of the zone's *reference city*
        # (e.g. Berlin for all of Germany, Moscow Mean Time "MMT" for Europe/Moscow which also
        # covers St Petersburg, Kazan...). In the Russian Empire / early USSR every town kept its
        # own mean time, so the astrologically correct offset is the birth place's own mean time:
        # longitude / 15 (+ the DST hour of 1917-1919 if tzdb has one).
        warnings.append("local_mean_time")
        if lon is not None:
            dst_part = chosen.dst() or dt.timedelta(0)
            if dst_part:
                warnings.append("historical_mean_time")
            lmt = dt.timedelta(seconds=round(lon * 240.0)) + dst_part
            utc = (naive - lmt).replace(tzinfo=UTC)
            off = round(lmt.total_seconds() / 3600.0, 6)
            details.update({"utc_offset_hours": off, "lmt_from_longitude": True})

    if tz_name in EX_USSR_ZONES:
        if d.year < 1970:
            warnings.append("ussr_pre_1970_low_confidence")
        if dt.date(1991, 3, 1) <= d <= dt.date(1992, 3, 31):
            warnings.append("ussr_1991_transition")
        if dt.date(1941, 6, 22) <= d <= dt.date(1944, 12, 31) and tz_name.startswith("Europe/"):
            warnings.append("ussr_wartime_1941_1944")
        if dt.date(1930, 6, 1) <= d <= dt.date(1930, 7, 1):
            warnings.append("ussr_1930_decree_introduced")
    if tz_name in MERGED_LINKS:
        warnings.append("tz_zone_merged")
        details["merged_into"] = MERGED_LINKS[tz_name]
    rc = _regime_change_near(z, naive)
    if rc:
        warnings.append("tz_regime_change")
        details["regime_changes"] = rc["changes"]
    if "local_mean_time" not in warnings and abs(off * 4 - round(off * 4)) > 1e-6:
        # other historical mean-time offsets (e.g. Moscow Mean Time 1880-1919)
        warnings.append("historical_mean_time")
    return {"utc": utc, "utc_offset_hours": off, "time_warnings": warnings,
            "tz_details": details, "alternatives": alternatives}


def fmt_offset(h: float) -> str:
    sign = "+" if h >= 0 else "−"
    m = int(round(abs(h) * 60))
    return f"UTC{sign}{m // 60}" + (f":{m % 60:02d}" if m % 60 else "")


RISKY = {"ussr_wartime_1941_1944", "dst_ambiguous", "dst_nonexistent", "ussr_1991_transition", "tz_regime_change", "local_mean_time",
         "historical_mean_time", "ussr_pre_1970_low_confidence", "tz_zone_merged", "tz_place_mismatch"}


def confirm_text_ru(date: str, place_label: str, offset_h: float, warnings: List[str]) -> Optional[str]:
    """Russian UX prompt asking the user to confirm the offset (None if nothing risky)."""
    if not RISKY & set(warnings):
        return None
    d = dt.date.fromisoformat(date)
    when = d.strftime("%d.%m.%Y")
    if "local_mean_time" in warnings:
        return (f"{when} в месте «{place_label}» ещё не было поясного времени: считаем по местному среднему "
                f"солнечному времени ({fmt_offset(offset_h)}). Если в документе указано другое время, поправьте.")
    if "dst_nonexistent" in warnings:
        return (f"В ночь на {when} часы переводили вперёд, и указанного времени по часам не существовало. "
                f"Уточните время по документу или выберите вариант смещения.")
    if "dst_ambiguous" in warnings:
        return (f"В ночь на {when} часы переводили назад, и это время было дважды. "
                f"По нашим данным — {fmt_offset(offset_h)} (первый раз). Верно?")
    return f"По нашим данным {when} в месте «{place_label}» действовало {fmt_offset(offset_h)}. Верно?"


def utc_to_local(utc: dt.datetime, tz_name: str) -> dt.datetime:
    return utc.astimezone(get_zone(tz_name))


def offset_at(date: str, time: str, tz_name: str) -> float:
    return local_to_utc(date, time, tz_name)["utc_offset_hours"]


def transitions(tz_name: str, start: dt.datetime, end: dt.datetime, step_hours: int = 1) -> List[Dict]:
    """Enumerate offset transitions (hour resolution) — used in tests and the docs table."""
    z = get_zone(tz_name)
    t = start.replace(tzinfo=UTC) if start.tzinfo is None else start
    end = end.replace(tzinfo=UTC) if end.tzinfo is None else end
    prev = t.astimezone(z).utcoffset()
    out = []
    while t < end:
        t2 = t + dt.timedelta(hours=step_hours)
        o = t2.astimezone(z).utcoffset()
        if o != prev:
            out.append({"utc": t2.strftime("%Y-%m-%dT%H:%MZ"), "from": _offset_h(prev), "to": _offset_h(o),
                        "abbr": t2.astimezone(z).tzname()})
            prev = o
        t = t2
    return out
