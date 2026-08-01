"""
Seed seasonal & event-based experiences across all 69 wilayas.
Keeps curated hand-written experiences and fills remaining gaps
programmatically to reach ~450+ total.

Run after seed_providers.py, seed_experiences_db.py, seed_more_experiences.py.
"""

import sys
import uuid
from datetime import date

import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://athar:athar_pass@localhost:5434/athar_db"

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi",
    5: "Batna", 6: "Béjaïa", 7: "Biskra", 8: "Béchar",
    9: "Blida", 10: "Bouira", 11: "Tamanrasset", 12: "Tébessa",
    13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou", 16: "Alger",
    17: "Djelfa", 18: "Jijel", 19: "Sétif", 20: "Saïda",
    21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba", 24: "Guelma",
    25: "Constantine", 26: "Médéa", 27: "Mostaganem", 28: "M'Sila",
    29: "Mascara", 30: "Ouargla", 31: "Oran", 32: "El Bayadh",
    33: "Illizi", 34: "Bordj Bou Arréridj", 35: "Boumerdès", 36: "El Tarf",
    37: "Tindouf", 38: "Tissemsilt", 39: "El Oued", 40: "Khenchela",
    41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Aïn Defla",
    45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa", 48: "Relizane",
    49: "Timimoun", 50: "Béni Abbès", 51: "Aïn Salah", 52: "Aïn Guezzam",
    53: "Touggourt", 54: "Djanet", 55: "El M'Ghair", 56: "El Meniaa",
    57: "Ouled Djellal", 58: "Bordj Badji Mokhtar",
    59: "Aflou", 60: "El Abiodh Sidi Cheikh", 61: "El Aricha",
    62: "El Kantara", 63: "Barika", 64: "Bou Saâda",
    65: "Bir El Ater", 66: "Ksar El Boukhari",
    67: "Ksar Chellala", 68: "Aïn Oussera", 69: "Messaad",
}

SEASONS_DATA = {
    "spring": (("2026-03-01", "2026-05-31"), [3, 4, 5, 6, 9, 10]),
    "summer": (("2026-06-01", "2026-09-30"), [6, 7, 8, 1, 2]),
    "autumn": (("2026-09-01", "2026-11-30"), [5, 4, 3, 6, 9, 10, 11]),
    "winter": (("2026-12-01", "2027-02-28"), [1, 2, 3, 5, 10, 11]),
}

# ── Hand-curated seasonal experiences ─────────────────────────

SPRING = [
    ("hiking", "Printemps kabyle — Randonnée des cédraies", 15,
     "Balade printanière à travers les forêts de cèdres du Djurdjura en pleine floraison.",
     "Tizi Ouzou centre", 1500, 6, 12),
    ("hiking", "Sentier des fleurs — Parc national de Theniet El Had", 14,
     "Randonnée au milieu des champs de fleurs sauvages au printemps.",
     "Theniet El Had", 1200, 4, 15),
    ("cultural", "Festival des cerises de Larbaâ Nath Irathen", 15,
     "Découverte du festival annuel des cerises avec dégustations et animations.",
     "Larbaâ Nath Irathen", 800, 3, 30),
    ("cultural", "Printemps de Timgad — Festival des arts", 5,
     "Festival culturel au printemps dans l'antique cité romaine de Timgad.",
     "Timgad", 1000, 4, 50),
    ("food", "Safari des asperges sauvages — Saïda", 20,
     "Cueillette et dégustation d'asperges sauvages dans les monts de Saïda.",
     "Saïda centre", 1000, 5, 10),
    ("food", "Randonnée gourmande — Huile d'olive fraîche", 6,
     "Découverte des oliveraies de Béjaïa avec dégustation d'huile d'olive nouvelle.",
     "Béjaïa port", 1800, 4, 15),
    ("tour", "Circuit des oasis — Printemps saharien", 11,
     "Circuit de 3 jours dans le Hoggar au printemps, températures idéales.",
     "Tamanrasset", 25000, 72, 8),
    ("tour", "Les gorges du Rhoufi — Printemps", 7,
     "Exploration des gorges du Rhoufi et des oasis de l'Aurès au printemps.",
     "Biskra", 4000, 8, 12),
    ("wellness", "Thermes de Guelma — Cure printanière", 24,
     "Cure thermale dans les sources chaudes de Guelma au printemps.",
     "Guelma centre", 3000, 24, 20),
    ("adventure", "Via ferrata de Chréa — Printemps", 9,
     "Via ferrata dans le parc national de Chréa au printemps.",
     "Chréa", 2000, 5, 8),
]

SUMMER = [
    ("hiking", "Ascension du Lalla Khedidja — Été", 6,
     "Ascension du plus haut sommet de Kabylie (2308 m) en été.",
     "Tizi Ouzou", 2000, 8, 10),
    ("tour", "Circuit Les stations balnéaires de l'Est", 23,
     "Circuit de 5 jours: Annaba, Skikda, El Kala, plages et parcs nationaux.",
     "Annaba centre", 18000, 120, 15),
    ("tour", "Plages secrètes de la côte ouest", 31,
     "Découverte des criques et plages sauvages entre Oran et Kristel.",
     "Oran", 5000, 6, 12),
    ("food", "Dégustation de figues de barbarie — Sétif", 19,
     "Dégustation de figues de barbarie fraîches dans les hauts plateaux.",
     "Sétif centre", 500, 2, 20),
    ("cultural", "Festival international de Timgad", 5,
     "Festival annuel de musique et théâtre dans le théâtre romain de Timgad (juillet).",
     "Timgad", 1500, 4, 100),
    ("cultural", "Festival de Djemila", 19,
     "Festival culturel dans le site antique de Djemila (août).",
     "Djemila", 1200, 4, 80),
    ("adventure", "Nuits berbères — Campement dans l'Aurès", 5,
     "Campement estival dans les monts de l'Aurès avec contes et musique.",
     "Batna", 3500, 24, 15),
    ("tour", "Journée plage + snorkeling — Les Andalouses", 31,
     "Journée sur la plage des Andalouses avec snorkeling et déjeuner poisson.",
     "Les Andalouses", 2500, 6, 20),
    ("tour", "Excursion en bateau — Îles Habibas", 31,
     "Excursion en bateau vers les Îles Habibas, réserve marine protégée.",
     "Oran port", 4000, 6, 12),
    ("tour", "Plage de Sidi Fredj — Détente et sports nautiques", 16,
     "Journée à la plage de Sidi Fredj avec jet-ski, paddle et parachute ascensionnel.",
     "Sidi Fredj", 3000, 6, 30),
    ("tour", "Cap Sigli — Randonnée côtière", 6,
     "Randonnée sur le cap Sigli avec vue panoramique sur la mer Méditerranée.",
     "Béjaïa", 1500, 5, 15),
    ("tour", "Les plages de Zéralda — Détente et loisirs", 16,
     "Journée plage avec parasols, sports nautiques et restaurants de poisson.",
     "Zéralda", 2000, 6, 25),
]

AUTUMN = [
    ("food", "Festival des dattes — Touggourt", 53,
     "Festival des dattes avec dégustation des meilleures variétés du Sud.",
     "Touggourt", 800, 3, 50),
    ("food", "Récolte des olives — Kabylie", 15,
     "Participation à la récolte des olives et visite de la huilerie traditionnelle.",
     "Tizi Ouzou", 1200, 5, 15),
    ("cultural", "S'biba Festival — Djanet", 54,
     "Festival traditionnel touareg S'biba, célébration du nouvel an agraire.",
     "Djanet", 2000, 3, 30),
    ("cultural", "Fantasia — Tbourida en Oranie", 22,
     "Spectacle de fantasia (tbourida) avec cavaliers en tenue traditionnelle.",
     "Sidi Bel Abbès", 1500, 3, 40),
    ("adventure", "Traversée du Tassili — Automne", 33,
     "Expédition de 5 jours dans le Tassili n'Ajjer aux températures clémentes.",
     "Djanet", 35000, 120, 6),
    ("tour", "Circuit des oasis du Mzab", 47,
     "Circuit de 2 jours dans la vallée du Mzab (Ghardaïa, Beni Isguen, Melika).",
     "Ghardaïa", 8000, 48, 12),
    ("tour", "Route des Ziban — Palmeraies de Biskra", 7,
     "Visite des palmeraies de Biskra et des oasis alentour à la saison des dattes.",
     "Biskra", 3500, 6, 15),
    ("wellness", "Thermes de Hammam Meskhoutine", 24,
     "Bain thermal dans les sources chaudes de Hammam Meskhoutine (98°C).",
     "Hammam Meskhoutine", 2000, 4, 30),
    ("hiking", "Forêt d'Akfadou — Automne aux couleurs flamboyantes", 6,
     "Randonnée en forêt d'Akfadou avec ses couleurs d'automne exceptionnelles.",
     "Akfadou", 1200, 5, 12),
    ("cultural", "Mouloud — Célébration à Tlemcen", 13,
     "Célébration du Mouloud avec traditions locales et medersas.",
     "Tlemcen", 500, 3, 50),
]

WINTER = [
    ("adventure", "Ski au Djurdjura — Tikjda", 15,
     "Journée de ski sur les pentes du Djurdjura à la station de Tikjda.",
     "Tikjda", 3500, 6, 20),
    ("adventure", "Ski de fond — Chréa", 9,
     "Ski de fond dans le parc national de Chréa, domaine skiable d'Algérie.",
     "Chréa", 3000, 5, 20),
    ("tour", "Hoggar en hiver — Nuits glacées sous les étoiles", 11,
     "Circuit hivernal dans le Hoggar (températures idéales la journée, nuits froides).",
     "Tamanrasset", 28000, 72, 8),
    ("tour", "Sahara winter expedition — Grand Erg Oriental", 39,
     "Expédition hivernale dans l'Erg Oriental avec bivouac et randonnée chamelière.",
     "El Oued", 22000, 48, 10),
    ("tour", "Circuit des ksour — Sud oranais", 32,
     "Circuit hivernal dans les ksour (villages fortifiés) du Sud oranais.",
     "El Bayadh", 6000, 24, 12),
    ("cultural", "Festival du Hoggar — Tamanrasset", 11,
     "Festival annuel du Hoggar, rassemblement des Touaregs avec musique et danses.",
     "Tamanrasset", 2000, 4, 50),
    ("food", "Couscous d'hiver — Atelier dégustation", 16,
     "Atelier de préparation et dégustation du couscous traditionnel algérien.",
     "Alger Casbah", 2500, 4, 10),
    ("wellness", "Hammam traditionnel — Cure d'hiver", 16,
     "Journée bien-être dans un hammam traditionnel d'Alger.",
     "Alger centre", 3000, 4, 10),
    ("hiking", "Randonnée hivernale — Monts de Trara", 13,
     "Randonnée dans les monts de Trara avec vue sur la Méditerranée.",
     "Tlemcen", 1000, 5, 12),
    ("adventure", "Nuit en yourte — Méchouar", 13,
     "Nuit en yourte traditionnelle dans les monts de Tlemcen.",
     "Tlemcen", 4000, 16, 8),
]

EVENTS = [
    ("cultural", "Festival international de la musique arabe — Tlemcen", 13,
     "Festival international de la musique arabe, hommage aux grands maîtres.",
     "Tlemcen centre", 2000, 3, date(2026, 6, 20), date(2026, 6, 28)),
    ("cultural", "Journées du patrimoine — Tipaza", 42,
     "Visites guidées des sites archéologiques de Tipaza.",
     "Tipaza", 500, 6, date(2026, 4, 18), date(2026, 4, 20)),
    ("food", "Salon du chocolat — Alger", 16,
     "Salon international du chocolat et de la pâtisserie à Alger.",
     "Alger", 1500, 4, date(2026, 10, 10), date(2026, 10, 13)),
    ("cultural", "Fête de la mer — Jijel", 18,
     "Fête annuelle de la mer avec défilés nautiques et poisson grillé.",
     "Jijel port", 1000, 6, date(2026, 7, 10), date(2026, 7, 15)),
    ("food", "Semaine de l'olive — Sidi Bel Abbès", 22,
     "Dégustations et ateliers autour de l'olive et de l'huile d'olive.",
     "Sidi Bel Abbès", 500, 3, date(2026, 11, 1), date(2026, 11, 7)),
    ("cultural", "Festival du théâtre amazigh — Béjaïa", 6,
     "Festival du théâtre amazigh avec troupes de toute l'Afrique du Nord.",
     "Béjaïa", 1000, 5, date(2026, 6, 1), date(2026, 6, 7)),
    ("adventure", "Rallye des dunes — Ouargla", 30,
     "Randonnée 4x4 dans les dunes de l'Erg Oriental.",
     "Ouargla", 12000, 24, date(2026, 11, 1), date(2027, 2, 28)),
    ("cultural", "Festival de la gharnata — Tlemcen", 13,
     "Festival de la musique gharnata (andalouse) de Tlemcen.",
     "Tlemcen", 1500, 4, date(2026, 8, 15), date(2026, 8, 22)),
    ("food", "Fête du méchoui — Laghouat", 3,
     "Grand méchoui traditionnel dans la steppe de Laghouat.",
     "Laghouat", 2000, 5, date(2026, 4, 1), date(2026, 4, 30)),
    ("cultural", "Carnaval d'El Oued — Défilé des oasis", 39,
     "Carnaval annuel d'El Oued avec chars décorés et costumes traditionnels.",
     "El Oued", 800, 4, date(2026, 12, 25), date(2026, 12, 30)),
    ("adventure", "Vol en montgolfière — Biskra", 7,
     "Vol en montgolfière au-dessus des palmeraies de Biskra au lever du soleil.",
     "Biskra", 10000, 3, date(2026, 3, 1), date(2026, 5, 30)),
    ("cultural", "Moussem de Tantan — Béchar", 8,
     "Rassemblement traditionnel des tribus du Sud-ouest algérien.",
     "Béchar", 1500, 4, date(2026, 9, 1), date(2026, 9, 15)),
    ("food", "Fête du couscous — Souk Ahras", 41,
     "Festival du couscous dans sa variante souk-ahrassienne.",
     "Souk Ahras", 1000, 3, date(2026, 5, 1), date(2026, 5, 15)),
    ("cultural", "Rencontres cinématographiques — Annaba", 23,
     "Festival du film méditerranéen d'Annaba.",
     "Annaba", 1500, 5, date(2026, 10, 1), date(2026, 10, 7)),
    ("adventure", "Descente de l'oued — Ghoufi", 7,
     "Descente en rappel des gorges du Ghoufi avec guide spéléologue.",
     "Ghoufi", 5000, 6, date(2026, 4, 1), date(2026, 6, 30)),
    ("cultural", "Fête de la musique — Alger", 16,
     "Concert géant place des Martyrs avec artistes algériens et internationaux.",
     "Alger centre", 500, 4, date(2026, 6, 21), date(2026, 6, 21)),
    ("cultural", "Nouvel an berbère (Yennayer) — Kabylie", 15,
     "Célébration du Nouvel An berbère avec repas traditionnel (12 janvier).",
     "Tizi Ouzou", 1500, 3, date(2027, 1, 11), date(2027, 1, 12)),
    ("cultural", "Fête de l'oasis — Adrar", 1,
     "Festival célébrant la culture oasienne avec courses de dromadaires.",
     "Adrar", 1200, 3, date(2026, 3, 15), date(2026, 3, 20)),
    ("tour", "Journée du patrimoine — Constantine", 25,
     "Visite guidée des ponts et monuments de Constantine.",
     "Constantine", 1000, 4, date(2026, 5, 1), date(2026, 5, 15)),
    ("cultural", "Festival du reggae — Djanet", 54,
     "Festival de reggae au cœur du Tassili, rencontre des cultures.",
     "Djanet", 2000, 4, date(2026, 11, 1), date(2026, 11, 5)),
]

# ── Generator templates ──────────────────────────────────────

CATEGORY_TEMPLATES = {
    "tour": {
        "titles": [
            "Circuit découverte de {name}",
            "Tour guidé de {name} et ses environs",
            "Visite complète de la wilaya de {name}",
            "Les incontournables de {name}",
            "Circuit culturel à {name}",
        ],
        "desc": "Circuit guidé à travers les sites emblématiques de {name}. "
                "Une immersion complète dans le patrimoine, la culture et les paysages de la région.",
    },
    "hiking": {
        "titles": [
            "Randonnée dans les monts de {name}",
            "Balade nature à {name}",
            "Sentier découverte de {name}",
            "Randonnée guidée — {name}",
        ],
        "desc": "Randonnée à travers les paysages naturels de {name}. "
                "Parcours adapté à tous les niveaux avec un guide local expérimenté.",
    },
    "cultural": {
        "titles": [
            "Immersion culturelle à {name}",
            "Découverte des traditions de {name}",
            "Patrimoine et artisanat de {name}",
            "Visite des sites historiques de {name}",
        ],
        "desc": "Découverte du riche patrimoine culturel de {name}. "
                "Visite des sites historiques, rencontre avec les artisans locaux.",
    },
    "food": {
        "titles": [
            "Dégustation des spécialités de {name}",
            "Tour gastronomique de {name}",
            "Atelier cuisine traditionnelle de {name}",
            "Marchés et saveurs de {name}",
        ],
        "desc": "Voyage culinaire à travers les saveurs de {name}. "
                "Dégustation des plats traditionnels et visite des marchés locaux.",
    },
    "adventure": {
        "titles": [
            "Aventure extrême à {name}",
            "Expédition dans les monts de {name}",
            "Défi nature — {name}",
        ],
        "desc": "Une expérience d'aventure inoubliable à {name}. "
                "Encadrée par des guides professionnels, équipement fourni.",
    },
    "wellness": {
        "titles": [
            "Détente et bien-être à {name}",
            "Journée spa à {name}",
            "Retraite bien-être dans la nature de {name}",
        ],
        "desc": "Journée de détente et de soins à {name}. "
                "Hammam traditionnel, massage et relaxation en pleine nature.",
    },
}

SEASON_SUFFIX = {
    "spring": " — Printemps",
    "summer": " — Été",
    "autumn": " — Automne",
    "winter": " — Hiver",
}

SEASON_DATES = {
    "spring": ("2026-03-01", "2026-05-31"),
    "summer": ("2026-06-01", "2026-09-30"),
    "autumn": ("2026-09-01", "2026-11-30"),
    "winter": ("2026-12-01", "2027-02-28"),
}

CATEGORY_DEFAULTS = {
    "tour": {"price": 2500, "dur": 6, "max_p": 15},
    "hiking": {"price": 1500, "dur": 5, "max_p": 12},
    "cultural": {"price": 1200, "dur": 4, "max_p": 20},
    "food": {"price": 1500, "dur": 3, "max_p": 15},
    "adventure": {"price": 4000, "dur": 8, "max_p": 8},
    "wellness": {"price": 3000, "dur": 4, "max_p": 10},
}


def fetch_wilaya_profile(cur):
    """Get per-wilaya POI counts to determine relevant categories."""
    cur.execute("""
        SELECT w.id,
               COUNT(DISTINCT CASE WHEN p.category IN ('beach','mountain','natural','park') THEN p.id END) as nature_pois,
               COUNT(DISTINCT CASE WHEN p.category IN ('cultural','historical','museum','religious') THEN p.id END) as culture_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'beach' THEN p.id END) as beach_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'mountain' THEN p.id END) as mountain_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'historical' THEN p.id END) as historical_pois
        FROM wilayas w
        LEFT JOIN pois p ON p.wilaya_id = w.id
        GROUP BY w.id
        ORDER BY w.id
    """)
    profile = {}
    for row in cur.fetchall():
        wid, nature, culture, beach, mtn, hist = row
        relevant = {"tour": True, "cultural": culture > 5, "food": True}
        if mtn > 3 or nature > 10:
            relevant["hiking"] = True
            relevant["adventure"] = True
        if beach > 0:
            relevant["wellness"] = True
        if culture > 20 or hist > 10:
            relevant["tour"] = True
            relevant["cultural"] = True
        profile[wid] = relevant
    return profile


def generate_programmatic(wilaya_profile, existing_wilaya_seasons):
    """Generate experiences for every wilaya×season×category combination."""
    generated = []
    for wid, name in WILAYA_NAMES.items():
        profile = wilaya_profile.get(wid, {"tour": True, "cultural": True, "food": True})
        for season, (sd, ed) in SEASON_DATES.items():
            suffix = SEASON_SUFFIX[season]
            for cat, template in CATEGORY_TEMPLATES.items():
                if not profile.get(cat, False):
                    continue
                # Check if this wilaya+season+category already has a curated entry
                if wid in existing_wilaya_seasons.get(season, set()) and cat in existing_wilaya_seasons.get(season + "_cats", {}).get(wid, set()):
                    continue
                # Weighted category priority: not all (wilaya×season×category) combos
                # We do 2-3 categories per wilaya per season
                import random
                r = random.Random(wid * 100 + hash(season) + hash(cat))
                if r.random() > 0.65:
                    continue
                import random as rnd
                r2 = rnd.Random(wid * 1000 + hash(season) + hash(cat))
                title_tpl = r2.choice(template["titles"])
                title = title_tpl.format(name=name) + suffix
                desc = template["desc"].format(name=name)
                defaults = CATEGORY_DEFAULTS[cat]
                generated.append((
                    cat, title, wid, desc,
                    f"{name} centre",
                    defaults["price"] + r2.randint(-500, 1500),
                    defaults["dur"] + r2.randint(-1, 2),
                    defaults["max_p"] + r2.randint(-3, 5),
                    season, sd, ed,
                ))
    return generated


def main():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # Fetch provider users
    cur.execute("SELECT id FROM users WHERE phone = '+213500000001'")
    guide_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000002'")
    agency_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000003'")
    admin_row = cur.fetchone()

    provider_id = (guide_row or agency_row or admin_row)
    if not provider_id:
        print("ERROR: No provider users found. Run seed_providers.py first.")
        sys.exit(1)
    guide_id = guide_row[0] if guide_row else provider_id[0]
    agency_id = agency_row[0] if agency_row else provider_id[0]

    # Fetch existing wilayas
    cur.execute("SELECT id FROM wilayas")
    existing_wilayas = {row[0] for row in cur.fetchall()}

    # Track existing seasonal entries to avoid duplicates
    cur.execute("SELECT wilaya_id, season, category FROM experiences WHERE season IS NOT NULL")
    existing_wilaya_seasons = {}
    for wid, season, cat in cur.fetchall():
        existing_wilaya_seasons.setdefault(season, set()).add(wid)
        existing_wilaya_seasons.setdefault(season + "_cats", {}).setdefault(wid, set()).add(cat)

    experiences = []

    def add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, start_d, end_d, exp_type=None):
        if wid not in existing_wilayas:
            return
        provider = guide_id if cat in ("hiking", "adventure") else agency_id
        experiences.append((
            uuid.uuid4(), provider, cat, title, desc, wid,
            meeting, None, None, price, dur, max_p, lang,
            None, None, "active", season, start_d, end_d,
        ))

    # Hand-curated seasonal
    for season, data in [("spring", SPRING), ("summer", SUMMER), ("autumn", AUTUMN), ("winter", WINTER)]:
        sd, ed = SEASON_DATES[season]
        for row in data:
            cat, title, wid, desc, meeting, price, dur, max_p = row
            add(cat, title, wid, desc, meeting, price, dur, max_p, "FR", season, sd, ed)

    # Events
    for row in EVENTS:
        cat, title, wid, desc, meeting, price, dur, sd, ed = row
        season = "spring" if 3 <= sd.month <= 5 else "summer" if 6 <= sd.month <= 8 else "autumn" if 9 <= sd.month <= 11 else "winter"
        add(cat, title, wid, desc, meeting, price, dur, 30, "FR", season, sd.isoformat(), ed.isoformat())

    # Programmatic generation
    wilaya_profile = fetch_wilaya_profile(cur)
    prog = generate_programmatic(wilaya_profile, existing_wilaya_seasons)
    for row in prog:
        cat, title, wid, desc, meeting, price, dur, max_p, season, sd, ed = row
        add(cat, title, wid, desc, meeting, price, dur, max_p, "FR", season, sd, ed)

    # Coverage: ensure every wilaya has at least 2 seasonal experiences
    covered = existing_wilaya_seasons
    for wid in WILAYA_NAMES:
        if wid not in existing_wilayas:
            continue
        has_any = any(wid in covered.get(s, set()) for s in ("spring", "summer", "autumn", "winter"))
        if has_any:
            continue
        name = WILAYA_NAMES[wid]
        # Add 2 coverage entries
        for cat, season in [("tour", "spring"), ("cultural", "summer")]:
            sd, ed = SEASON_DATES[season]
            title = f"Circuit découverte de {name}"
            desc = f"Visite guidée complète de la wilaya de {name} avec ses principaux sites."
            add(cat, title, wid, desc, f"{name} centre", 2000, 5, 12, "FR", season, sd, ed)

    # Bulk insert
    insert_sql = """
        INSERT INTO experiences
            (id, provider_id, category, title, description, wilaya_id,
             meeting_point, meeting_point_lat, meeting_point_lng,
             price_dzd, duration_hours, max_participants,
             language, included, what_to_bring, status,
             season, start_date, end_date)
        VALUES %s
    """

    rows = []
    for e in experiences:
        rows.append((
            str(e[0]), str(e[1]), e[2], e[3], e[4], e[5],
            e[6], e[7], e[8], e[9], e[10], e[11],
            e[12], e[13], e[14], e[15],
            e[16], e[17], e[18],
        ))

    try:
        execute_values(cur, insert_sql, rows, page_size=100)
        conn.commit()
        print(f"Inserted {len(rows)} seasonal/event-based experiences")

        cur.execute("SELECT season, COUNT(*) FROM experiences WHERE season IS NOT NULL GROUP BY season ORDER BY season")
        print("\n=== By season ===")
        for r in cur.fetchall():
            print(f"  {r[0]:8s}: {r[1]}")
        cur.execute("SELECT COUNT(DISTINCT wilaya_id) FROM experiences WHERE season IS NOT NULL")
        print(f"\n  Wilayas covered: {cur.fetchone()[0]} / {len(existing_wilayas)}")
        cur.execute("SELECT COUNT(*) FROM experiences WHERE season IS NOT NULL")
        print(f"  Total seasonal: {cur.fetchone()[0]}")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
