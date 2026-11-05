"""Build the compact offline city index engine/data/cities_ru.tsv.gz from GeoNames dumps.

Source: https://download.geonames.org/export/dump/ (GeoNames, CC BY 4.0, https://www.geonames.org/)
Inputs (downloaded manually, see engine/README.md):
  cities5000.zip, cities1000.zip, alternateNamesV2.zip, admin1CodesASCII.txt, countryInfo.txt
Usage:
  python -I scripts/build_geo.py <download_dir> <output.tsv.gz>

What it keeps:
  * every city with population >= 5000 worldwide (cities5000),
  * plus every settlement with population >= 1000 in the former USSR (cities1000 filtered),
  * Russian names (isolanguage=ru) incl. historic ones (Куйбышев, Свердловск, Ленинград ...),
  * Russian names of regions (admin1) and countries for disambiguation.
"""
import csv, gzip, io, sys, zipfile, os

EX_USSR = {"RU", "UA", "BY", "KZ", "UZ", "KG", "TJ", "TM", "AZ", "AM", "GE", "MD", "LT", "LV", "EE"}


def read_cities(zpath, member, keep):
    out = {}
    with zipfile.ZipFile(zpath) as z, z.open(member) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 19:
                continue
            if not keep(p):
                continue
            out[int(p[0])] = p
    return out


def main(src, dst):
    cities = read_cities(os.path.join(src, "cities5000.zip"), "cities5000.txt", lambda p: True)
    extra = read_cities(os.path.join(src, "cities1000.zip"), "cities1000.txt", lambda p: p[8] in EX_USSR)
    for k, v in extra.items():
        cities.setdefault(k, v)
    # admin1 + country geoname ids for Russian labels
    admin1 = {}
    with open(os.path.join(src, "admin1CodesASCII.txt"), encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 4:
                admin1[p[0]] = (p[1], int(p[3]))
    country = {}
    with open(os.path.join(src, "countryInfo.txt"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) > 16 and p[16]:
                country[p[0]] = (p[4], int(p[16]))
    need = set(cities) | {g for _, g in admin1.values()} | {g for _, g in country.values()}
    ru = {}       # gid -> list of (name, preferred, short, colloquial, historic)
    with zipfile.ZipFile(os.path.join(src, "alternateNamesV2.zip")) as z, z.open("alternateNamesV2.txt") as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 8 or p[2] != "ru":
                continue
            gid = int(p[1])
            if gid not in need:
                continue
            ru.setdefault(gid, []).append((p[3], p[4] == "1", p[5] == "1", p[6] == "1", p[7] == "1"))

    def best_ru(gid):
        names = ru.get(gid) or []
        if not names:
            return ""
        cur = [n for n in names if not n[4] and not n[3]] or names
        pref = [n for n in cur if n[1] and not n[2]] or [n for n in cur if n[1]] or cur
        return pref[0][0]

    rows = 0
    with gzip.open(dst, "wt", encoding="utf-8", compresslevel=9) as out:
        w = csv.writer(out, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, escapechar="\\")
        w.writerow(["geoname_id", "name", "name_ru", "lat", "lon", "country", "country_ru", "admin1", "admin1_ru",
                    "population", "tz", "feature", "alt_ru", "alt_hist_ru", "alt_other"])
        for gid, p in cities.items():
            cc = p[8]
            a1name, a1gid = admin1.get(f"{cc}.{p[10]}", ("", 0))
            cname, cgid = country.get(cc, ("", 0))
            names = ru.get(gid, [])
            alt_ru = sorted({n[0] for n in names if not n[4]})
            alt_hist = sorted({n[0] for n in names if n[4]})
            # other alternate names: keep only Cyrillic ones (Ukrainian/Belarusian/Kazakh spellings) + ascii
            others = sorted({a for a in p[3].split(",") if a and any("Ѐ" <= ch <= "ӿ" for ch in a)} - set(alt_ru) - set(alt_hist))
            clean = lambda s: s.replace("\t", " ").replace("|", "/")
            w.writerow([gid, clean(p[1]), clean(best_ru(gid)), p[4], p[5], cc, clean(best_ru(cgid) or cname), clean(a1name),
                        clean(best_ru(a1gid) or a1name), p[14] or "0", p[17], p[7],
                        "|".join(map(clean, alt_ru)), "|".join(map(clean, alt_hist)), "|".join(map(clean, others[:30]))])
            rows += 1
    print("rows", rows, "with ru names", sum(1 for g in cities if g in ru))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
