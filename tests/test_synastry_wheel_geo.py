import re
import xml.etree.ElementTree as ET

import pytest

from astro_engine import geo
from astro_engine.calc import natal_chart, point_map, angdiff
from astro_engine.synastry import synastry_report
from astro_engine.wheel import render_wheel, _spread

A = {"date": "1987-04-12", "time": "14:35", "place": {"lat": 53.2001, "lon": 50.15, "tz": "Europe/Samara"}}
B = {"date": "1985-09-03", "time": "08:10", "place": {"lat": 55.7558, "lon": 37.6173, "tz": "Europe/Moscow"}}


def test_synastry_aspects_consistent():
    r = synastry_report(A, B)
    p1, p2 = point_map(r["charts"][0]), point_map(r["charts"][1])
    ang = {"conjunction": 0, "opposition": 180, "trine": 120, "square": 90, "sextile": 60}
    assert r["aspects"]
    for a in r["aspects"]:
        sep = abs(angdiff(p1[a["a"]]["lon"], p2[a["b"]]["lon"]))
        assert abs(abs(sep - ang[a["type"]]) - a["orb"]) < 0.01 and a["orb"] <= a["orb_max"]
    ov = r["house_overlays"]
    assert len(ov) == 2 * 13 and {o["person"] for o in ov} == {1, 2}
    assert all(1 <= o["house"] <= 12 for o in ov)


def test_synastry_no_overlays_if_time_unknown():
    b = dict(B, time=None, time_known=False)
    r = synastry_report(A, b)
    assert r["house_overlays"] == []
    assert any(a.get("uncertain") for a in r["aspects"] if a["b"] == "moon")


def test_wheel_valid_svg_and_css_vars():
    svg = render_wheel(natal_chart(A))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    for v in ("--aw-bg", "--aw-fire", "--aw-asp-trine", "--aw-planet"):
        assert v in svg
    assert len(re.findall(r'data-point="', svg)) == 13
    assert len(re.findall(r'class="aw-[a-z]+ aw-cusp"', svg)) == 12


def test_wheel_unknown_time():
    svg = render_wheel(natal_chart(dict(A, time=None, time_known=False)))
    ET.fromstring(svg)
    assert "aw-cusp" not in svg


def test_spread_separates_glyphs():
    lons = [10.0, 10.5, 11.0, 11.2, 200.0, 359.8, 0.1]
    out = _spread(lons, 7.0)
    s = sorted(out)
    gaps = [b - a for a, b in zip(s, s[1:])] + [s[0] + 360 - s[-1]]
    assert min(gaps) >= 7.0 - 1e-6
    assert all(abs(angdiff(o, l)) < 25 for o, l in zip(out, lons))


@pytest.mark.parametrize("q,gid", [("Самара", 499099), ("Куйбышев", 499099), ("Ленинград", 498817),
                                   ("Свердловск", 1486209), ("Сталинград", 472757), ("Москва", 524901),
                                   ("Киев", 703448), ("Алма-Ата", 1526384), ("Мурманск", 524305),
                                   ("samara", 499099), ("Санкт Петербург", 498817), ("Нижний", 520555)])
def test_geo_search(q, gid):
    assert geo.search(q)[0]["geoname_id"] == gid


# Big ex-USSR cities: GeoNames tz must agree with the coordinate-based zone (timezonefinder).
CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск",
          "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар",
          "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Ярославль",
          "Владивосток", "Махачкала", "Томск", "Оренбург", "Кемерово", "Новокузнецк", "Астрахань", "Киров",
          "Калининград", "Мурманск", "Норильск", "Якутск", "Симферополь", "Киев", "Харьков", "Одесса", "Днепр",
          "Львов", "Запорожье", "Минск", "Алматы", "Астана", "Караганда", "Шымкент", "Ташкент", "Баку", "Тбилиси",
          "Ереван", "Кишинёв", "Рига", "Вильнюс", "Таллин", "Бишкек", "Душанбе", "Ашхабад"]


@pytest.mark.parametrize("q", CITIES)
def test_geo_tz_matches_coordinates(q):
    r = geo.search(q, limit=1)[0]
    tz_coord = geo.tz_for(r["lat"], r["lon"])
    links = {("Europe/Kyiv", "Europe/Kiev")}
    assert r["tz"] == tz_coord or (r["tz"], tz_coord) in links or (tz_coord, r["tz"]) in links, (q, r["tz"], tz_coord)
