import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)
BIRTH = {"name": "Анна", "date": "1987-04-12", "time": "14:35", "time_known": True,
         "place": {"query": "Самара", "geoname_id": 499099, "lat": 53.2001, "lon": 50.15, "country": "RU",
                   "tz": "Europe/Samara"}, "house_system": "P"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_natal_contract_fields():
    r = client.post("/natal", json=BIRTH)
    assert r.status_code == 200
    c = r.json()
    for k in ("schema", "input", "utc", "utc_offset_hours", "tz_source", "time_warnings", "julian_day_ut",
              "points", "houses", "angles", "aspects", "summary", "engine"):
        assert k in c, k
    assert c["schema"] == "natal/0.1"
    ids = [p["id"] for p in c["points"]]
    assert ids == ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto",
                   "true_node", "chiron", "lilith", "asc", "mc"]
    for p in c["points"]:
        for k in ("id", "name_ru", "lon", "sign", "sign_ru", "deg_in_sign", "house", "retrograde", "speed", "dignity"):
            assert k in p
    assert len(c["houses"]) == 12 and set(c["angles"]) == {"asc", "mc", "dsc", "ic"}
    for a in c["aspects"]:
        assert a["type"] in {"conjunction", "opposition", "trine", "square", "sextile"}
        for k in ("a", "b", "type", "type_ru", "angle", "orb", "applying"):
            assert k in a
    s = c["summary"]
    assert sum(s["elements"].values()) == 10 and sum(s["modalities"].values()) == 10
    assert set(s["big_three"]) == {"sun", "moon", "asc"}
    assert r.headers["X-Calc-Ms"]


def test_natal_bad_input():
    assert client.post("/natal", json={"date": "1987-02-30", "time": "10:00", "place": BIRTH["place"]}).status_code == 422
    assert client.post("/natal", json={"date": "1987-02-10", "time": "10:00",
                                       "place": {"lat": 1, "lon": 1, "tz": "Mars/Olympus"}}).status_code == 422


def test_transits_api():
    r = client.post("/transits", json={"birth": BIRTH, "from": "2026-11-01", "to": "2027-10-31"})
    assert r.status_code == 200
    t = r.json()
    assert t["schema"] == "transits/0.1" and t["events"] and t["sky_events"]
    e = t["events"][0]
    for k in ("date_exact", "window", "transit", "natal", "type", "orb_max", "retro_pass", "importance"):
        assert k in e


def test_synastry_api():
    p2 = dict(BIRTH, date="1985-09-03", time="08:10")
    r = client.post("/synastry", json={"person1": BIRTH, "person2": p2})
    assert r.status_code == 200
    j = r.json()
    assert j["aspects"] and j["house_overlays"]
    assert {"a_person", "a", "b_person", "b", "type", "orb"} <= set(j["aspects"][0])


def test_wheel_api():
    r = client.post("/wheel.svg", json=BIRTH)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.startswith("<svg") and "var(--aw-fire" in r.text


def test_geo_api():
    r = client.get("/geo/search", params={"q": "Куйбышев"})
    assert r.status_code == 200
    j = r.json()
    assert j["results"][0]["geoname_id"] == 499099 and "GeoNames" in j["attribution"]
