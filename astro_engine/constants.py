"""Reference tables: signs, points, dignities, aspects, orbs. All documented in docs/ENGINE.md."""

SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo",
         "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
SIGNS_RU = ["Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
            "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"]
SIGN_ELEMENT = {s: e for s, e in zip(SIGNS, ["fire", "earth", "air", "water"] * 3)}
SIGN_MODALITY = {s: m for s, m in zip(SIGNS, ["cardinal", "fixed", "mutable"] * 4)}

PLANETS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
EXTRA_POINTS = ["true_node", "chiron", "lilith"]
ANGLE_POINTS = ["asc", "mc"]
ALL_POINTS = PLANETS + EXTRA_POINTS + ANGLE_POINTS

POINT_RU = {
    "sun": "Солнце", "moon": "Луна", "mercury": "Меркурий", "venus": "Венера", "mars": "Марс",
    "jupiter": "Юпитер", "saturn": "Сатурн", "uranus": "Уран", "neptune": "Нептун", "pluto": "Плутон",
    "true_node": "Северный узел (истинный)", "chiron": "Хирон", "lilith": "Лилит (средняя)",
    "asc": "Асцендент", "mc": "Середина неба (MC)",
}

GLYPH = {
    "sun": "☉", "moon": "☽", "mercury": "☿", "venus": "♀", "mars": "♂", "jupiter": "♃",
    "saturn": "♄", "uranus": "♅", "neptune": "♆", "pluto": "♇", "true_node": "☊",
    "chiron": "⚷", "lilith": "⚸", "asc": "Asc", "mc": "MC",
}
SIGN_GLYPH = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]

# Dignities. Domicile includes both traditional and modern rulers (Scorpio: Mars + Pluto,
# Aquarius: Saturn + Uranus, Pisces: Jupiter + Neptune). Exaltations only for the 7 classical
# planets (outer-planet exaltations are not agreed upon among schools).
DOMICILE = {
    "sun": ["leo"], "moon": ["cancer"], "mercury": ["gemini", "virgo"], "venus": ["taurus", "libra"],
    "mars": ["aries", "scorpio"], "jupiter": ["sagittarius", "pisces"], "saturn": ["capricorn", "aquarius"],
    "uranus": ["aquarius"], "neptune": ["pisces"], "pluto": ["scorpio"],
}
EXALTATION = {"sun": "aries", "moon": "taurus", "mercury": "virgo", "venus": "pisces", "mars": "capricorn",
              "jupiter": "cancer", "saturn": "libra"}


def _opp(sign):
    return SIGNS[(SIGNS.index(sign) + 6) % 12]


DETRIMENT = {p: [_opp(s) for s in ss] for p, ss in DOMICILE.items()}
FALL = {p: _opp(s) for p, s in EXALTATION.items()}

# Modern sign rulers (for the Ascendant ruler / dominant planet scoring).
SIGN_RULER = {"aries": "mars", "taurus": "venus", "gemini": "mercury", "cancer": "moon", "leo": "sun",
              "virgo": "mercury", "libra": "venus", "scorpio": "pluto", "sagittarius": "jupiter",
              "capricorn": "saturn", "aquarius": "uranus", "pisces": "neptune"}
# Traditional rulers (Scorpio=Mars, Aquarius=Saturn, Pisces=Jupiter). Used for the dominant-planet score so that it
# agrees with the "chart ruler" shown in reports (docs/READING_RULES.md §3); SIGN_RULER above stays modern.
TRAD_RULER = dict(SIGN_RULER, scorpio="mars", aquarius="saturn", pisces="jupiter")

ASPECTS = [  # (type, angle, Russian)
    ("conjunction", 0, "соединение"),
    ("opposition", 180, "оппозиция"),
    ("trine", 120, "трин"),
    ("square", 90, "квадрат"),
    ("sextile", 60, "секстиль"),
]
ASPECT_RU = {t: r for t, _, r in ASPECTS}
ASPECT_ANGLE = {t: a for t, a, _ in ASPECTS}

# Natal orbs in degrees, by body class and aspect. Orb of a pair = max of the two bodies,
# except when one body is a "minor point" (node, Chiron, Lilith): then the minor point's orb applies.
ORB_CLASS = {
    "sun": "lum", "moon": "lum",
    "mercury": "pers", "venus": "pers", "mars": "pers",
    "jupiter": "soc", "saturn": "soc",
    "uranus": "outer", "neptune": "outer", "pluto": "outer",
    "true_node": "minor", "chiron": "minor", "lilith": "minor",
    "asc": "angle", "mc": "angle",
}
ORBS = {
    #          conj  opp  trine square sextile
    "lum":   {"conjunction": 10, "opposition": 10, "trine": 8, "square": 8, "sextile": 6},
    "pers":  {"conjunction": 8, "opposition": 8, "trine": 7, "square": 7, "sextile": 5},
    "soc":   {"conjunction": 7, "opposition": 7, "trine": 6, "square": 6, "sextile": 4},
    "outer": {"conjunction": 6, "opposition": 6, "trine": 5, "square": 5, "sextile": 4},
    "angle": {"conjunction": 6, "opposition": 6, "trine": 5, "square": 5, "sextile": 4},
    "minor": {"conjunction": 3, "opposition": 3, "trine": 2, "square": 2, "sextile": 2},
}
SYNASTRY_ORB_FACTOR = 0.75   # synastry orbs = natal orbs x 0.75


def pair_orb(a: str, b: str, aspect: str, factor: float = 1.0) -> float:
    ca, cb = ORB_CLASS[a], ORB_CLASS[b]
    if "minor" in (ca, cb):
        return ORBS["minor"][aspect] * factor
    return max(ORBS[ca][aspect], ORBS[cb][aspect]) * factor
