# astro-engine

Расчётное ядро сервиса: натальная карта, транзиты и небесные события, синастрия, SVG-колесо, офлайн-поиск городов. Работает на Swiss Ephemeris (pyswisseph). Отдельный HTTP-сервис под **AGPL-3.0** (см. `LICENSE`); веб-платформа обращается к нему только по HTTP. Контракт данных — `../docs/CHART_SCHEMA.md` v0.1. Архитектура, точность и ограничения описаны в `../docs/ENGINE.md`, часовые пояса — в `TIMEZONES.md`.

## Установка
```bash
cd engine
python3 -m venv .venv                 # Python 3.9+ (проверено на 3.9.6; прод — 3.11+ на Linux)
.venv/bin/pip install -r requirements-dev.txt
# опционально: независимая сверка с astronomy-engine (нужен Node 18+)
(cd tests/crosscheck && npm ci)
```
Данные уже лежат в репозитории:
- `ephe/sepl_18.se1`, `semo_18.se1`, `seas_18.se1` — эфемериды Swiss Ephemeris на 1800–2400 гг., около 2 МБ (источник: github.com/aloistr/swisseph/ephe). Если файлов нет, движок сам переходит на встроенный Moshier: планеты и Луна ошибаются меньше чем на 5″, но Хирона нет (`warnings: ["chiron_unavailable"]`).
- `data/cities_ru.tsv.gz` — 76 181 населённый пункт, 2,6 МБ, собран `scripts/build_geo.py` из дампов GeoNames (CC BY 4.0). Состав: все города мира с населением от 5000 и все пункты бывшего СССР от 1000, русские названия, в том числе исторические (Куйбышев, Свердловск…). Как пересобрать:
  ```bash
  mkdir -p /tmp/gn && cd /tmp/gn && for f in cities5000.zip cities1000.zip alternateNamesV2.zip admin1CodesASCII.txt countryInfo.txt; do curl -O https://download.geonames.org/export/dump/$f; done
  cd - && .venv/bin/python -I scripts/build_geo.py /tmp/gn data/cities_ru.tsv.gz
  ```

## Запуск
```bash
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8088      # прогрев ~1,5 с (индекс городов + полигоны зон)
.venv/bin/python -m pytest -q                                  # 199 тестов, ~4 с
.venv/bin/python -m pytest -q -s tests/test_reference_charts.py tests/test_crosscheck_astronomy_engine.py  # печатает отклонения
```
Переменные окружения: `ASTRO_EPHE_PATH` (папка с .se1), `ASTRO_GEO_DATA` (файл городов).

## HTTP API
| Метод | Путь | Тело / параметры | Ответ |
|---|---|---|---|
| GET | `/health` | — | версия, tzdb, лицензия |
| POST | `/natal` | `BirthInput` | `NatalChart` |
| POST | `/transits` | `{"birth": BirthInput \| "chart": NatalChart, "from": "2026-11-01", "to": "2027-10-31", "tz"?, "planets"?, "targets"?, "orbs"?, "sky"?: true}` | `TransitReport` |
| POST | `/synastry` | `{"person1": BirthInput, "person2": BirthInput}` | `SynastryReport` |
| POST | `/wheel.svg` | `BirthInput` или `{"chart": NatalChart, "size": 600, "aspects": true}` | `image/svg+xml` |
| GET | `/geo/search?q=Куйбышев&limit=10&country=RU` | — | `{"results": [...], "attribution": "..."}` |

Ошибки ввода возвращаются с кодом 422 и `detail`. В каждом ответе есть заголовок `X-Calc-Ms` (время расчёта) и `X-Source-Code` (ссылка на исходники по AGPL §13: https://github.com/therefactoredmind/natalnayakarta-engine).

Пример:
```bash
curl -s -X POST localhost:8088/natal -H 'content-type: application/json' \
  -d '{"name":"Анна","date":"1987-04-12","time":"14:35","time_known":true,
       "place":{"query":"Самара","geoname_id":499099,"lat":53.2001,"lon":50.15,"country":"RU","tz":"Europe/Samara"},
       "house_system":"P"}'
```
Расширения `BirthInput`. Все необязательные, предложены в v0.2 контракта:
- `house_system`: `P` Плацидус, `K` Кох, `O` Порфирий, `W` целые знаки;
- `fold`: 0 или 1 — выбор при двояком времени перевода часов;
- `utc_offset_override`: смещение в часах, подтверждённое пользователем;
- `place` можно задать только через `geoname_id` или `query`, тогда координаты и зону подставит движок.

Колесо стилизуется CSS-переменными `--aw-*` на родительском элементе, например `--aw-bg`, `--aw-fire`, `--aw-water`, `--aw-planet`, `--aw-asp-trine`. Полный список — в `astro_engine/wheel.py`.

## Структура
```
astro_engine/  calc.py (натал), timezones.py, geo.py, transits.py, synastry.py, wheel.py, constants.py (орбисы, достоинства)
server.py      FastAPI
tests/         pytest: точность (reference_charts, crosscheck), пояса, граничные случаи, транзиты, API
scripts/       build_geo.py
ephe/ data/    эфемериды и города
```

## Лицензии и атрибуция
- Код движка: AGPL-3.0 (`LICENSE`). Swiss Ephemeris © Astrodienst AG: AGPL или Swiss Ephemeris Professional License (`ephe/LICENSE.swisseph.txt`).
- Геоданные: **«Geographical data © GeoNames (geonames.org), CC BY 4.0»** — эту строку нужно показывать на сайте рядом с поиском города или в подвале. Её же отдаёт `/geo/search` в поле `attribution`.
- tzdb — public domain; timezonefinder — MIT; FastAPI — MIT; astronomy-engine (только в тестах) — MIT.
