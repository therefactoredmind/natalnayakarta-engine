"""Historical UTC offsets for USSR / Russia / Ukraine / Kazakhstan etc.

Expected values come from the legal acts / well-documented history (not from tzdb itself):
  * USSR decree time since 21.06.1930 (Moscow UTC+3, no DST until 1981);
  * Resolution of the USSR Council of Ministers No. 925 of 24.10.1980: summer time from 01.04.1981 00:00
    to 01.10.1981 00:00, then from 1984 last Sunday of March 2:00 -> last Sunday of September 3:00;
  * 31.03.1991: decree hour abolished (Moscow summer 1991 = UTC+3, winter 1991/92 = UTC+2),
    19.01.1992: restored (Moscow UTC+3 / +4);
  * Kuibyshev (Samara) region on Moscow time 26.03.1989 - 20.10.1991;
  * Ukraine moved to Kyiv (EET-based) time 01.07.1990;
  * Federal law 107-FZ (2011): permanent "summer" time from 27.03.2011 (Moscow UTC+4);
    law 248-FZ (2014): from 26.10.2014 Moscow UTC+3, Samara/Udmurtia stay UTC+4;
  * regional laws 2016: Astrakhan & Ulyanovsk 27.03.2016 -> UTC+4, Saratov 04.12.2016 -> UTC+4,
    Barnaul 27.03.2016 / Tomsk 29.05.2016 / Novosibirsk 24.07.2016 -> UTC+7;
    Volgograd 28.10.2018 -> UTC+4, back to UTC+3 on 27.12.2020;
  * Belarus permanent UTC+3 since 27.03.2011; Crimea on Moscow time 30.03.2014;
  * Kazakhstan: DST abolished 2005; single time zone UTC+5 since 01.03.2024 (Almaty was UTC+6).
"""
import pytest

from astro_engine.timezones import local_to_utc

CASES = [
    # zone, date, time, expected offset, note
    ("Europe/Moscow", "1958-07-15", "12:00", 3, "decree time, no DST in 1950s"),
    ("Europe/Moscow", "1960-01-10", "12:00", 3, "decree time winter"),
    ("Europe/Kyiv", "1958-07-15", "12:00", 3, "Ukraine on Moscow time"),
    ("Europe/Samara", "1959-07-15", "12:00", 4, "Kuibyshev decree time"),
    ("Asia/Yekaterinburg", "1958-07-15", "12:00", 5, "Sverdlovsk decree time"),
    ("Asia/Almaty", "1960-07-15", "12:00", 6, "Alma-Ata decree time"),
    ("Europe/Moscow", "1981-03-31", "23:30", 3, "last minutes before the first Soviet DST"),
    ("Europe/Moscow", "1981-04-01", "01:30", 4, "first Soviet summer time"),
    ("Europe/Moscow", "1981-07-01", "12:00", 4, "summer 1981"),
    ("Europe/Moscow", "1981-10-01", "01:00", 3, "after summer 1981 ended"),
    ("Europe/Kyiv", "1981-07-01", "12:00", 4, "Ukraine summer 1981 (Moscow time)"),
    ("Europe/Samara", "1985-07-01", "12:00", 5, "Kuibyshev summer"),
    ("Europe/Samara", "1990-01-15", "12:00", 3, "Samara on Moscow time 1989-1991"),
    ("Europe/Samara", "1991-12-01", "12:00", 4, "Samara time restored 20.10.1991"),
    ("Europe/Moscow", "1991-06-15", "12:00", 3, "summer 1991 without decree hour"),
    ("Europe/Moscow", "1991-12-01", "12:00", 2, "winter 1991/92, decree hour abolished"),
    ("Europe/Moscow", "1992-02-01", "12:00", 3, "decree hour restored 19.01.1992"),
    ("Europe/Moscow", "1992-07-01", "12:00", 4, "summer 1992"),
    ("Europe/Kyiv", "1990-08-01", "12:00", 3, "Ukraine on Kyiv summer time since 01.07.1990"),
    ("Europe/Kyiv", "1992-12-01", "12:00", 2, "Ukraine EET winter"),
    ("Europe/Kaliningrad", "1992-07-01", "12:00", 3, "Kaliningrad EEST"),
    ("Europe/Kaliningrad", "1992-12-01", "12:00", 2, "Kaliningrad EET"),
    ("Europe/Moscow", "2010-12-01", "12:00", 3, "before 2011 reform"),
    ("Europe/Moscow", "2011-12-01", "12:00", 4, "permanent summer time 2011-2014"),
    ("Europe/Moscow", "2013-07-01", "12:00", 4, "permanent summer time 2011-2014"),
    ("Europe/Moscow", "2014-11-01", "12:00", 3, "after 26.10.2014"),
    ("Europe/Samara", "2012-01-15", "12:00", 4, "Samara 2010-2014: UTC+4"),
    ("Europe/Samara", "2015-01-15", "12:00", 4, "Samara stayed UTC+4 in 2014"),
    ("Asia/Yekaterinburg", "2013-01-15", "12:00", 6, "Yekaterinburg 2011-2014: UTC+6"),
    ("Asia/Yekaterinburg", "2015-01-15", "12:00", 5, "Yekaterinburg after 2014: UTC+5"),
    ("Europe/Minsk", "2012-01-15", "12:00", 3, "Belarus permanent UTC+3"),
    ("Europe/Simferopol", "2014-06-01", "12:00", 4, "Crimea Moscow time summer 2014"),
    ("Europe/Simferopol", "2015-06-01", "12:00", 3, "Crimea MSK"),
    ("Europe/Astrakhan", "2016-03-01", "12:00", 3, "before 27.03.2016"),
    ("Europe/Astrakhan", "2016-04-15", "12:00", 4, "after 27.03.2016"),
    ("Europe/Ulyanovsk", "2016-03-01", "12:00", 3, "before 27.03.2016"),
    ("Europe/Ulyanovsk", "2016-04-15", "12:00", 4, "after 27.03.2016"),
    ("Europe/Saratov", "2016-11-01", "12:00", 3, "before 04.12.2016"),
    ("Europe/Saratov", "2017-01-15", "12:00", 4, "after 04.12.2016"),
    ("Europe/Volgograd", "2018-06-01", "12:00", 3, "before 28.10.2018"),
    ("Europe/Volgograd", "2019-06-01", "12:00", 4, "2018-2020 UTC+4"),
    ("Europe/Volgograd", "2021-06-01", "12:00", 3, "after 27.12.2020"),
    ("Asia/Barnaul", "2016-04-15", "12:00", 7, "Altai krai 27.03.2016"),
    ("Asia/Tomsk", "2016-04-15", "12:00", 6, "Tomsk before 29.05.2016"),
    ("Asia/Tomsk", "2016-06-15", "12:00", 7, "Tomsk after 29.05.2016"),
    ("Asia/Novosibirsk", "2016-07-01", "12:00", 6, "Novosibirsk before 24.07.2016"),
    ("Asia/Novosibirsk", "2016-08-01", "12:00", 7, "Novosibirsk after 24.07.2016"),
    ("Asia/Almaty", "2004-07-01", "12:00", 7, "Kazakhstan DST until 2004"),
    ("Asia/Almaty", "2006-07-01", "12:00", 6, "no DST since 2005"),
    ("Asia/Almaty", "2024-01-15", "12:00", 6, "before 01.03.2024"),
    ("Asia/Almaty", "2024-04-01", "12:00", 5, "single zone UTC+5"),
    ("Europe/Kyiv", "2011-12-01", "12:00", 2, "Ukraine 2011 DST cancellation was reverted"),
]


@pytest.mark.parametrize("tz,date,time,expected,note", CASES)
def test_historical_offsets(tz, date, time, expected, note):
    r = local_to_utc(date, time, tz)
    assert r["utc_offset_hours"] == expected, f"{tz} {date} {time}: {note}; got {r['utc_offset_hours']}"


def test_1981_spring_gap_is_nonexistent():
    r = local_to_utc("1981-04-01", "00:30", "Europe/Moscow")
    assert "dst_nonexistent" in r["time_warnings"]
    assert {a["utc_offset_hours"] for a in r["alternatives"]} == {3, 4}


def test_1981_autumn_overlap_is_ambiguous():
    r = local_to_utc("1981-09-30", "23:30", "Europe/Moscow")
    assert "dst_ambiguous" in r["time_warnings"]
    assert r["utc_offset_hours"] == 4               # default: first occurrence (summer time)
    r2 = local_to_utc("1981-09-30", "23:30", "Europe/Moscow", fold=1)
    assert r2["utc_offset_hours"] == 3


def test_2014_autumn_ambiguous():
    r = local_to_utc("2014-10-26", "01:30", "Europe/Moscow")
    assert "dst_ambiguous" in r["time_warnings"] and r["utc_offset_hours"] == 4


def test_ussr_1991_flag():
    r = local_to_utc("1991-06-15", "12:00", "Europe/Samara")
    assert "ussr_1991_transition" in r["time_warnings"] and "tz_regime_change" in r["time_warnings"]


def test_pre_1970_flag():
    assert "ussr_pre_1970_low_confidence" in local_to_utc("1958-07-15", "12:00", "Europe/Moscow")["time_warnings"]


def test_regime_change_flag_volgograd():
    assert "tz_regime_change" in local_to_utc("2019-06-01", "12:00", "Europe/Volgograd")["time_warnings"]
    assert "tz_regime_change" not in local_to_utc("2005-06-01", "12:00", "Europe/Volgograd")["time_warnings"]


def test_lmt_uses_birth_longitude():
    # Ulm 1879 (Einstein): Germany had no standard time before 1893 -> LMT of Ulm (10°E = +0:40)
    r = local_to_utc("1879-03-14", "11:30", "Europe/Berlin", lon=10.0)
    assert "local_mean_time" in r["time_warnings"]
    assert r["utc"].strftime("%H:%M") == "10:50"


def test_merged_zone_flag():
    assert "tz_zone_merged" in local_to_utc("1990-08-01", "12:00", "Europe/Zaporozhye")["time_warnings"]


def test_bad_zone():
    from astro_engine.timezones import TimezoneError
    with pytest.raises(TimezoneError):
        local_to_utc("1990-01-01", "12:00", "Europe/Nowhere")
