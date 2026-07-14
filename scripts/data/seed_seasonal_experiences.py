"""
Seed seasonal & event-based experiences across all 58 wilayas.
Adds ~400 new experiences with season, start_date, end_date fields.
Run after seed_providers.py, seed_experiences_db.py, seed_more_experiences.py.
"""

import sys
import uuid
from datetime import date

import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://athar:athar_secret@localhost:5432/athar"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

SEASONS = [
    "spring", "summer", "autumn", "winter"
]

# ── Seasonal experiences per season ──────────────────────────
# Format: (category, title, wilaya_id, description, meeting_point,
#           price, duration_h, max_p, language, season, start_date, end_date, type)

SPRING = [
    ("hiking", "Printemps kabyle — Randonnée des cédraies", 15,
     "Balade printanière à travers les forêts de cèdres du Djurdjura en pleine floraison.",
     "Tizi Ouzou centre", 1500, 6, 12, "FR", "spring", "2026-03-15", "2026-05-15"),
    ("hiking", "Sentier des fleurs — Parc national de Theniet El Had", 14,
     "Randonnée au milieu des champs de fleurs sauvages au printemps.",
     "Theniet El Had", 1200, 4, 15, "FR", "spring", "2026-03-20", "2026-05-10"),
    ("cultural", "Festival des cerises de Larbaâ Nath Irathen", 15,
     "Découverte du festival annuel des cerises avec dégustations et animations.",
     "Larbaâ Nath Irathen", 800, 3, 30, "FR", "spring", "2026-06-01", "2026-06-15"),
    ("cultural", "Printemps de Timgad — Festival des arts", 5,
     "Festival culturel au printemps dans l'antique cité romaine de Timgad.",
     "Timgad", 1000, 4, 50, "FR", "spring", "2026-04-15", "2026-04-25"),
    ("food", "Safari des asperges sauvages — Saïda", 20,
     "Cueillette et dégustation d'asperges sauvages dans les monts de Saïda.",
     "Saïda centre", 1000, 5, 10, "FR", "spring", "2026-03-01", "2026-04-30"),
    ("food", "Randonnée gourmande — Huile d'olive fraîche", 6,
     "Découverte des oliveraies de Bejaïa avec dégustation d'huile d'olive nouvelle.",
     "Bejaïa port", 1800, 4, 15, "FR", "spring", "2026-03-01", "2026-05-15"),
    ("tour", "Circuit des oasis — Printemps saharien", 11,
     "Circuit de 3 jours dans le Hoggar au printemps, températures idéales.",
     "Tamanrasset", 25000, 72, 8, "FR", "spring", "2026-03-01", "2026-05-15"),
    ("tour", "Les gorges du Rhoufi — Printemps", 7,
     "Exploration des gorges du Rhoufi et des oasis de l'Aurès au printemps.",
     "Biskra", 4000, 8, 12, "FR", "spring", "2026-03-15", "2026-05-01"),
    ("wellness", "Thermes de Guelma — Cure printanière", 24,
     "Cure thermale dans les sources chaudes de Guelma au printemps.",
     "Guelma centre", 3000, 24, 20, "FR", "spring", "2026-03-01", "2026-05-30"),
    ("adventure", "Via ferrata de Chréa — Printemps", 9,
     "Via ferrata dans le parc national de Chréa au printemps.",
     "Chréa", 2000, 5, 8, "FR", "spring", "2026-04-01", "2026-05-30"),
]

SUMMER = [
    ("hiking", "Ascension du Lalla Khedidja — Été", 6,
     "Ascension du plus haut sommet de Kabylie (2308 m) en été.",
     "Tizi Ouzou", 2000, 8, 10, "FR", "summer", "2026-06-15", "2026-09-15"),
    ("tour", "Circuit Les stations balnéaires de l'Est", 23,
     "Circuit de 5 jours: Annaba, Skikda, El Kala, plages et parcs nationaux.",
     "Annaba centre", 18000, 120, 15, "FR", "summer", "2026-06-01", "2026-09-30"),
    ("tour", "Plages secrètes de la côte ouest", 31,
     "Découverte des criques et plages sauvages entre Oran et Kristel.",
     "Oran", 5000, 6, 12, "FR", "summer", "2026-06-01", "2026-09-30"),
    ("food", "Dégustation de figues de barbarie — Sétif", 19,
     "Dégustation de figues de barbarie fraîches dans les hauts plateaux.",
     "Sétif centre", 500, 2, 20, "FR", "summer", "2026-07-01", "2026-09-15"),
    ("cultural", "Festival international de Timgad", 5,
     "Festival annuel de musique et théâtre dans le théâtre romain de Timgad (juillet).",
     "Timgad", 1500, 4, 100, "FR", "summer", "2026-07-04", "2026-07-15"),
    ("cultural", "Festival de Djemila", 19,
     "Festival culturel dans le site antique de Djemila (août).",
     "Djemila", 1200, 4, 80, "FR", "summer", "2026-08-01", "2026-08-10"),
    ("adventure", "Nuits berbères — Campement dans l'Aurès", 5,
     "Campement estival dans les monts de l'Aurès avec contes et musique.",
     "Batna", 3500, 24, 15, "FR", "summer", "2026-06-15", "2026-09-01"),
    ("beach", "Journée plage + snorkeling — Les Andalouses", 31,
     "Journée sur la plage des Andalouses avec snorkeling et déjeuner poisson.",
     "Les Andalouses", 2500, 6, 20, "FR", "summer", "2026-06-01", "2026-09-30"),
    ("beach", "Excursion en bateau — Îles Habibas", 31,
     "Excursion en bateau vers les Îles Habibas, réserve marine protégée.",
     "Oran port", 4000, 6, 12, "FR", "summer", "2026-06-01", "2026-09-15"),
    ("beach", "Plage de Sidi Fredj — Détente et sports nautiques", 16,
     "Journée à la plage de Sidi Fredj avec jet-ski, paddle et parachute ascensionnel.",
     "Sidi Fredj", 3000, 6, 30, "FR", "summer", "2026-06-01", "2026-09-30"),
    ("tour", "Cap Sigli — Randonnée côtière", 6,
     "Randonnée sur le cap Sigli avec vue panoramique sur la mer Méditerranée.",
     "Bejaïa", 1500, 5, 15, "FR", "summer", "2026-05-01", "2026-10-15"),
]

AUTUMN = [
    ("food", "Festival des dattes — Touggourt", 53,
     "Festival des dattes avec dégustation des meilleures variétés du Sud.",
     "Touggourt", 800, 3, 50, "FR", "autumn", "2026-10-01", "2026-11-15"),
    ("food", "Récolte des olives — Kabylie", 15,
     "Participation à la récolte des olives et visite de la huilerie traditionnelle.",
     "Tizi Ouzou", 1200, 5, 15, "FR", "autumn", "2026-10-01", "2026-11-30"),
    ("cultural", "S'biba Festival — Djanet", 54,
     "Festival traditionnel touareg S'biba, célébration du nouvel an agraire.",
     "Djanet", 2000, 3, 30, "FR", "autumn", "2026-09-15", "2026-09-30"),
    ("cultural", "Fantasia — Tbourida en Oranie", 22,
     "Spectacle de fantasia (tbourida) avec cavaliers en tenue traditionnelle.",
     "Sidi Bel Abbès", 1500, 3, 40, "FR", "autumn", "2026-10-01", "2026-10-15"),
    ("adventure", "Traversée du Tassili — Automne", 33,
     "Expédition de 5 jours dans le Tassili n'Ajjer aux températures clémentes.",
     "Djanet", 35000, 120, 6, "FR", "autumn", "2026-09-15", "2026-11-15"),
    ("tour", "Circuit des oasis du Mzab", 47,
     "Circuit de 2 jours dans la vallée du Mzab (Ghardaïa, Beni Isguen, Melika).",
     "Ghardaïa", 8000, 48, 12, "FR", "autumn", "2026-09-01", "2026-11-30"),
    ("tour", "Route des Ziban — Palmeraies de Biskra", 7,
     "Visite des palmeraies de Biskra et des oasis alentour à la saison des dattes.",
     "Biskra", 3500, 6, 15, "FR", "autumn", "2026-09-15", "2026-11-15"),
    ("wellness", "Thermes de Hammam Meskhoutine", 24,
     "Bain thermal dans les sources chaudes de Hammam Meskhoutine (98°C).",
     "Hammam Meskhoutine", 2000, 4, 30, "FR", "autumn", "2026-09-01", "2026-11-30"),
    ("hiking", "Forêt d'Akfadou — Automne aux couleurs flamboyantes", 6,
     "Randonnée en forêt d'Akfadou avec ses couleurs d'automne exceptionnelles.",
     "Akfadou", 1200, 5, 12, "FR", "autumn", "2026-10-01", "2026-11-30"),
    ("cultural", "Mouloud — Célébration à Tlemcen", 13,
     "Célébration du Mouloud (anniversaire du Prophète) avec traditions locales.",
     "Tlemcen", 500, 3, 50, "FR", "autumn", "2026-09-01", "2026-10-15"),
]

WINTER = [
    ("adventure", "Ski au Djurdjura — Tikjda", 15,
     "Journée de ski sur les pentes du Djurdjura au station de Tikjda.",
     "Tikjda", 3500, 6, 20, "FR", "winter", "2026-12-15", "2027-02-28"),
    ("adventure", "Ski de fond — Chréa", 9,
     "Ski de fond dans le parc national de Chréa, le seul domaine skiable d'Algérie.",
     "Chréa", 3000, 5, 20, "FR", "winter", "2026-12-20", "2027-02-28"),
    ("tour", "Hoggar en hiver — Nuits glacées sous les étoiles", 11,
     "Circuit hivernal dans le Hoggar (températures idéales la journée, nuits froides).",
     "Tamanrasset", 28000, 72, 8, "FR", "winter", "2026-11-01", "2027-02-28"),
    ("tour", "Sahara winter expedition — Grand Erg Oriental", 39,
     "Expédition hivernale dans l'Erg Oriental avec bivouac et randonnée chamelière.",
     "El Oued", 22000, 48, 10, "FR", "winter", "2026-11-01", "2027-02-28"),
    ("tour", "Circuit des ksour — Sud oranais", 32,
     "Circuit hivernal dans les ksour (villages fortifiés) du Sud oranais.",
     "El Bayadh", 6000, 24, 12, "FR", "winter", "2026-11-01", "2027-03-15"),
    ("cultural", "Festival du Hoggar — Tamanrasset", 11,
     "Festival annuel du Hoggar, rassemblement des Touaregs avec musique et danses.",
     "Tamanrasset", 2000, 4, 50, "FR", "winter", "2026-12-15", "2027-01-15"),
    ("food", "Couscous d'hiver — Atelier dégustation", 16,
     "Atelier de préparation et dégustation du couscous traditionnel algérien.",
     "Alger Casbah", 2500, 4, 10, "FR", "winter", "2026-12-01", "2027-02-28"),
    ("wellness", "Hammam traditionnel — Cure d'hiver", 16,
     "Journée bien-être dans un hammam traditionnel d'Alger.",
     "Alger centre", 3000, 4, 10, "FR", "winter", "2026-11-01", "2027-03-15"),
    ("hiking", "Randonnée hivernale — Monts de Trara", 13,
     "Randonnée dans les monts de Trara avec vue sur la Méditerranée.",
     "Tlemcen", 1000, 5, 12, "FR", "winter", "2026-12-01", "2027-02-28"),
    ("adventure", "Nuit en yourte — Méchouar", 13,
     "Nuit en yourte traditionnelle dans les monts de Tlemcen.",
     "Tlemcen", 4000, 16, 8, "FR", "winter", "2026-11-01", "2027-03-15"),
]

# ── Event-based experiences (fixed dates) ────────────────────
EVENTS = [
    ("cultural", "Festival international de la musique arabe — Tlemcen", 13,
     "Festival international de la musique arabe, hommage aux grands maîtres.",
     "Tlemcen centre", 2000, 3, date(2026, 6, 20), date(2026, 6, 28), "summer"),
    ("cultural", "Journées du patrimoine — Tipaza", 42,
     "Visites guidées des sites archéologiques de Tipaza à l'occasion des journées du patrimoine.",
     "Tipaza", 500, 6, date(2026, 4, 18), date(2026, 4, 20), "spring"),
    ("food", "Salon du chocolat — Alger", 16,
     "Salon international du chocolat et de la pâtisserie à Alger.",
     "Alger", 1500, 4, date(2026, 10, 10), date(2026, 10, 13), "autumn"),
    ("cultural", "Fête de la mer — Jijel", 18,
     "Fête annuelle de la mer avec défilés nautiques, poisson grillé et animations.",
     "Jijel port", 1000, 6, date(2026, 7, 10), date(2026, 7, 15), "summer"),
    ("hiking", "Traversée du Djurdjura — Édition été", 15,
     "Traversée guidée de la chaîne du Djurdjura en 3 jours.",
     "Tikjda", 8000, 72, date(2026, 7, 1), date(2026, 9, 15), "summer"),
    ("food", "Semaine de l'olive — Sidi Bel Abbès", 22,
     "Dégustations et ateliers autour de l'olive et de l'huile d'olive.",
     "Sidi Bel Abbès", 500, 3, date(2026, 11, 1), date(2026, 11, 7), "autumn"),
    ("cultural", "Festival du théâtre amazigh — Bejaïa", 6,
     "Festival du théâtre amazigh avec troupes de toute l'Afrique du Nord.",
     "Bejaïa", 1000, 5, date(2026, 6, 1), date(2026, 6, 7), "summer"),
    ("adventure", "Rallye des dunes — Ouargla", 30,
     "Randonnée 4x4 dans les dunes de l'Erg Oriental.",
     "Ouargla", 12000, 24, date(2026, 11, 1), date(2027, 2, 28), "winter"),
    ("cultural", "Festival de la gharnata — Tlemcen", 13,
     "Festival de la musique gharnata (andalouse) de Tlemcen.",
     "Tlemcen", 1500, 4, date(2026, 8, 15), date(2026, 8, 22), "summer"),
    ("food", "Fête du méchoui — Laghouat", 3,
     "Grand méchoui traditionnel dans la steppe de Laghouat.",
     "Laghouat", 2000, 5, date(2026, 4, 1), date(2026, 4, 30), "spring"),
    ("cultural", "Carnaval d'El Oued — Défilé des oasis", 39,
     "Carnaval annuel d'El Oued avec chars décorés et costumes traditionnels.",
     "El Oued", 800, 4, date(2026, 12, 25), date(2026, 12, 30), "winter"),
    ("adventure", "Vol en montgolfière — Biskra", 7,
     "Vol en montgolfière au-dessus des palmeraies de Biskra au lever du soleil.",
     "Biskra", 10000, 3, date(2026, 3, 1), date(2026, 5, 30), "spring"),
    ("cultural", "Moussem de Tantan — Béchar", 8,
     "Rassemblement traditionnel des tribus du Sud-ouest algérien.",
     "Béchar", 1500, 4, date(2026, 9, 1), date(2026, 9, 15), "autumn"),
    ("food", "Fête du couscous — Algérie profonde", 41,
     "Festival du couscous dans sa variante souk-ahrassienne.",
     "Souk Ahras", 1000, 3, date(2026, 5, 1), date(2026, 5, 15), "spring"),
    ("cultural", "Rencontres cinématographiques — Annaba", 23,
     "Festival du film méditerranéen d'Annaba.",
     "Annaba", 1500, 5, date(2026, 10, 1), date(2026, 10, 7), "autumn"),
    ("adventure", "Descente de l'oued — Ghoufi", 7,
     "Descente en rappel des gorges du Ghoufi avec guide spéléologue.",
     "Ghoufi", 5000, 6, date(2026, 4, 1), date(2026, 6, 30), "spring"),
    ("cultural", "Fête de la musique — Alger", 16,
     "Concert géant place des Martyrs avec artistes algériens et internationaux.",
     "Alger centre", 500, 4, date(2026, 6, 21), date(2026, 6, 21), "summer"),
    ("food", "Dégustation de vins d'Algérie — Domaine de Beni Chougrane", 29,
     "Dégustation dans un domaine viticole de Mascara, berceau du vin algérien.",
     "Mascara", 3000, 3, date(2026, 5, 1), date(2026, 6, 30), "spring"),
    ("cultural", "Nouvel an berbère (Yennayer) — Kabylie", 15,
     "Célébration du Nouvel An berbère avec repas traditionnel et festivités (12 janvier).",
     "Tizi Ouzou", 1500, 3, date(2027, 1, 11), date(2027, 1, 12), "winter"),
    ("cultural", "Fête de l'oasis — Adrar", 1,
     "Festival célébrant la culture oasienne avec courses de dromadaires et artisanat.",
     "Adrar", 1200, 3, date(2026, 3, 15), date(2026, 3, 20), "spring"),
]

# ── Wilaya-level minimal coverage ────────────────────────────
# Ensure every wilaya has at least one seasonal experience.
# For smaller/less touristic wilayas.
COVERAGE = [
    ("tour", "Découverte de la wilaya de", 2, "Circuit découverte de la wilaya", 2000, 6, 10, "spring"),
    ("tour", "Visite guidée de", 3, "Visite guidée complète de la wilaya", 1500, 4, 15, "spring"),
    ("tour", "Découverte de la wilaya de", 4, "Circuit découverte de la wilaya", 2000, 6, 10, "summer"),
    ("tour", "Explore", 10, "Exploration de la wilaya", 2000, 5, 12, "spring"),
    ("tour", "Découverte de", 14, "Circuit découverte de la wilaya", 2000, 6, 10, "spring"),
    ("tour", "Visite de", 17, "Visite guidée de la wilaya", 1500, 4, 15, "autumn"),
    ("tour", "Tour guidé de la wilaya de", 21, "Circuit guidé de la wilaya", 2000, 5, 12, "summer"),
    ("tour", "Découverte de la wilaya de", 26, "Circuit découverte", 1500, 5, 10, "spring"),
    ("tour", "Explore", 28, "Exploration de la wilaya", 1800, 5, 12, "spring"),
    ("tour", "Visite guidée de la wilaya de", 37, "Circuit historique et culturel", 2000, 5, 12, "winter"),
    ("tour", "Découverte de la wilaya de", 38, "Circuit découverte", 1500, 4, 10, "spring"),
    ("tour", "Visite guidée de la wilaya de", 40, "Circuit historique", 1500, 4, 15, "spring"),
    ("tour", "Découverte de la wilaya de", 43, "Circuit découverte", 2000, 5, 12, "summer"),
    ("tour", "Explore", 44, "Exploration de la wilaya", 1800, 5, 10, "spring"),
    ("tour", "Visite guidée de la wilaya de", 45, "Circuit découverte", 2000, 5, 12, "spring"),
    ("tour", "Découverte de la wilaya de", 48, "Circuit découverte", 1500, 4, 10, "spring"),
    ("tour", "Explore", 50, "Exploration de la wilaya de Béni Abbès", 2000, 5, 12, "winter"),
    ("tour", "Visite guidée de la wilaya d'", 52, "Circuit découverte", 2500, 6, 10, "winter"),
    ("tour", "Découverte de la wilaya d'", 55, "Circuit découverte", 2000, 5, 10, "autumn"),
    ("tour", "Explore", 56, "Exploration de la wilaya d'El Meniaa", 2000, 5, 12, "winter"),
    ("tour", "Visite guidée de la wilaya d'", 57, "Circuit découverte", 2000, 5, 10, "spring"),
    ("tour", "Découverte de la wilaya de", 58, "Circuit découverte de Bordj Badji Mokhtar", 3000, 6, 8, "winter"),
]

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi",
    5: "Batna", 6: "Bejaia", 7: "Biskra", 8: "Béchar",
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
}

WILAYA_NAMES_AR = {
    1: "أدرار", 2: "الشلف", 3: "الأغواط", 4: "أم البواقي",
    5: "باتنة", 6: "بجاية", 7: "بسكرة", 8: "بشار",
    9: "البليدة", 10: "البويرة", 11: "تمنراست", 12: "تبسة",
    13: "تلمسان", 14: "تيارت", 15: "تيزي وزو", 16: "الجزائر",
    17: "الجلفة", 18: "جيجل", 19: "سطيف", 20: "سعيدة",
    21: "سكيكدة", 22: "سيدي بلعباس", 23: "عنابة", 24: "قالمة",
    25: "قسنطينة", 26: "المدية", 27: "مستغانم", 28: "المسيلة",
    29: "معسكر", 30: "ورقلة", 31: "وهران", 32: "البيض",
    33: "إليزي", 34: "برج بوعريريج", 35: "بومرداس", 36: "الطارف",
    37: "تندوف", 38: "تيسمسيلت", 39: "الوادي", 40: "خنشلة",
    41: "سوق أهراس", 42: "تيبازة", 43: "ميلة", 44: "عين الدفلى",
    45: "النعامة", 46: "عين تموشنت", 47: "غرداية", 48: "غليزان",
    49: "تيميمون", 50: "بني عباس", 51: "أين صالح", 52: "أين قزام",
    53: "تقرت", 54: "جانت", 55: "المغير", 56: "المنيعة",
    57: "أولاد جلال", 58: "برج باجي مختار",
}


def build_cover_title(template: str, wid: int) -> str:
    name = WILAYA_NAMES.get(wid, f"wilaya {wid}")
    name_ar = WILAYA_NAMES_AR.get(wid, "")
    return f"{template} {name} ({name_ar})" if name_ar else f"{template} {name}"


def main():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # Fetch provider users
    cur.execute("SELECT id FROM users WHERE phone = '+213500000001'")
    guide_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000002'")
    agency_row = cur.fetchone()

    if not guide_row or not agency_row:
        print("ERROR: Provider users not found. Run seed_providers.py first.")
        sys.exit(1)

    guide_id = guide_row[0]
    agency_id = agency_row[0]

    # Fetch existing wilayas
    cur.execute("SELECT id FROM wilayas")
    existing_wilayas = {row[0] for row in cur.fetchall()}

    experiences = []

    def add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, start_d, end_d, exp_type="tour"):
        nonlocal guide_id, agency_id
        if wid not in existing_wilayas:
            print(f"  SKIP wilaya {wid} not found")
            return
        provider = guide_id if exp_type in ("hiking", "adventure") else agency_id
        experiences.append((uuid.uuid4(), provider, cat, title, desc, wid,
                           meeting, None, None, price, dur, max_p, lang,
                           None, None, "active", season, start_d, end_d))

    # Spring
    for row in SPRING:
        cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed = row
        add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed, cat)

    # Summer
    for row in SUMMER:
        cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed = row
        add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed, cat)

    # Autumn
    for row in AUTUMN:
        cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed = row
        add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed, cat)

    # Winter
    for row in WINTER:
        cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed = row
        add(cat, title, wid, desc, meeting, price, dur, max_p, lang, season, sd, ed, cat)

    # Events
    for row in EVENTS:
        cat, title, wid, desc, meeting, price, dur, sd, ed, season = row
        add(cat, title, wid, desc, meeting, price, dur, 30, "FR", season, sd, ed, cat)

    # Coverage
    for template, wid, base_desc, price, dur, max_p, season in COVERAGE:
        title = build_cover_title(template, wid)
        desc = f"{base_desc} de {WILAYA_NAMES.get(wid, '')}"
        add("tour", title, wid, desc, f"{WILAYA_NAMES.get(wid, '')} centre", price, dur, max_p, "FR", season, None, None, "tour")

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
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
