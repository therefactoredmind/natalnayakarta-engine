"""Swiss Ephemeris keeps its ephemeris path per thread; the server computes charts in a thread pool."""
import threading

from astro_engine.calc import natal_chart


def test_se_files_used_in_worker_thread():
    out = {}
    birth = {"date": "1990-06-15", "time": "12:30", "time_known": True, "place": {"lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow"}}

    def run():
        out["c"] = natal_chart(birth)

    t = threading.Thread(target=run)
    t.start()
    t.join()
    assert "SE files" in out["c"]["engine"]["ephemeris"]
    assert "chiron_unavailable" not in out["c"]["warnings"]
