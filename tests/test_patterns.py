"""Aspect patterns (docs/READING_RULES.md §2): detection on synthetic aspect lists and presence in a real chart."""
from astro_engine.calc import find_patterns, natal_chart


def asp(a, b, t):
    return {"a": a, "b": b, "type": t}


def test_t_square_apex():
    pats = find_patterns([asp("sun", "saturn", "opposition"), asp("sun", "mars", "square"), asp("saturn", "mars", "square")])
    assert pats == [{"type": "t_square", "points": ["sun", "saturn", "mars"], "apex": "mars"}]


def test_grand_trine():
    pats = find_patterns([asp("sun", "jupiter", "trine"), asp("jupiter", "neptune", "trine"), asp("sun", "neptune", "trine")])
    assert [p["type"] for p in pats] == ["grand_trine"]


def test_grand_cross_includes_t_squares():
    a = [asp("sun", "saturn", "opposition"), asp("moon", "mars", "opposition"),
         asp("sun", "moon", "square"), asp("sun", "mars", "square"), asp("saturn", "moon", "square"), asp("saturn", "mars", "square")]
    types = [p["type"] for p in find_patterns(a)]
    assert types.count("grand_cross") == 1 and types.count("t_square") == 4


def test_points_and_nodes_ignored():
    assert find_patterns([asp("sun", "asc", "opposition"), asp("sun", "true_node", "square"), asp("asc", "true_node", "square")]) == []


def test_summary_has_patterns():
    c = natal_chart({"date": "1990-04-12", "time": "14:35", "time_known": True,
                     "place": {"lat": 53.195, "lon": 50.1, "tz": "Europe/Samara"}})
    assert isinstance(c["summary"]["patterns"], list)
