"""HTTP API of astro-engine (AGPL-3.0). Run: uvicorn server:app --port 8088

POST /natal        body: BirthInput                         -> NatalChart
POST /transits     body: {"birth": BirthInput | "chart": NatalChart, "from": "YYYY-MM-DD", "to": "YYYY-MM-DD",
                          "tz": optional IANA, "planets": [...], "orbs": {...}, "sky": true} -> TransitReport
POST /synastry     body: {"person1": BirthInput, "person2": BirthInput} -> SynastryReport
POST /wheel.svg    body: BirthInput | {"chart": NatalChart, "size": 600}  -> image/svg+xml
GET  /geo/search?q=Самара&limit=10&country=RU                 -> {"results": [...], "attribution": ...}
GET  /health
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from astro_engine import __version__, geo
from astro_engine.calc import InputError, natal_chart
from astro_engine.synastry import synastry_report
from astro_engine.timezones import TZ_SOURCE, TimezoneError
from astro_engine.transits import transit_report
from astro_engine.wheel import render_wheel
import swisseph as swe

SOURCE_URL = "https://github.com/therefactoredmind/natalnayakarta-engine"  # AGPL §13: link to the running source (deploy/publish_engine.sh)

@asynccontextmanager
async def lifespan(app):
    warmup()
    yield


app = FastAPI(title="astro-engine", version=__version__, lifespan=lifespan,
              description="Natal charts, transits, synastry on Swiss Ephemeris. AGPL-3.0. Source: " + SOURCE_URL)


def warmup():
    geo.search("Москва")          # loads the city index (~0.7 s)
    geo.tz_for(55.75, 37.62)      # loads timezone polygons (~0.8 s)
    natal_chart({"date": "2000-01-01", "time": "12:00", "place": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}})


def _bad(e: Exception):
    raise HTTPException(status_code=422, detail=str(e))


def _chart_from(body: Dict[str, Any]) -> Dict:
    if "chart" in body and isinstance(body["chart"], dict) and body["chart"].get("schema") == "natal/0.1":
        return body["chart"]
    birth = body.get("birth", body)
    return natal_chart(birth)


@app.middleware("http")
async def timing(request, call_next):
    t = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Calc-Ms"] = f"{(time.perf_counter() - t) * 1000:.1f}"
    resp.headers["X-Source-Code"] = SOURCE_URL
    return resp


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "swisseph": swe.version, "tz_source": TZ_SOURCE,
            "geo_attribution": geo.ATTRIBUTION, "license": "AGPL-3.0", "source": SOURCE_URL}


@app.post("/natal")
def natal(body: Dict[str, Any] = Body(...)):
    try:
        return JSONResponse(natal_chart(body))
    except (InputError, TimezoneError, ValueError) as e:
        _bad(e)


@app.post("/transits")
def transits(body: Dict[str, Any] = Body(...)):
    try:
        chart = _chart_from(body)
        period = body.get("period") or {}
        d0 = body.get("from") or period.get("from")
        d1 = body.get("to") or period.get("to")
        if not d0 or not d1:
            raise InputError("from/to (or period.from/period.to) are required")
        return JSONResponse(transit_report(chart, d0, d1, tz=body.get("tz"), planets=body.get("planets"),
                                           targets=body.get("targets"), orbs=body.get("orbs"),
                                           sky=body.get("sky", True)))
    except (InputError, TimezoneError, ValueError, KeyError) as e:
        _bad(e)


@app.post("/synastry")
def synastry(body: Dict[str, Any] = Body(...)):
    try:
        return JSONResponse(synastry_report(body["person1"], body["person2"]))
    except (InputError, TimezoneError, ValueError, KeyError) as e:
        _bad(e)


@app.post("/wheel.svg")
def wheel(body: Dict[str, Any] = Body(...)):
    try:
        chart = _chart_from(body)
        size = int(body.get("size", 600))
        if not 200 <= size <= 2000:
            raise InputError("size must be 200..2000")
        svg = render_wheel(chart, size=size, aspects=body.get("aspects", True))
        return Response(svg, media_type="image/svg+xml")
    except (InputError, TimezoneError, ValueError, KeyError) as e:
        _bad(e)


@app.get("/geo/search")
def geo_search(q: str = Query(..., min_length=2, max_length=100), limit: int = Query(10, ge=1, le=50),
               country: str = Query(None, min_length=2, max_length=2)):
    return {"results": geo.search(q, limit=limit, country=country), "attribution": geo.ATTRIBUTION}
