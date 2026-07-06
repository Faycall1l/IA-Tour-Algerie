#!/usr/bin/env python3
"""
Comprehensive Algerian Transit Scraper Engine.
Harvests data from SETRAM, SEMA Metro, SNTF Trains, SOGRAL Buses, and OSM Nominatim.
Outputs: app/data/transit_nodes.json and app/data/transit_edges.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
OSM_SLEEP = 1.0

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "app" / "data"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TransitScraper/1.0",
    "Mozilla/5.0 (X11; Linux x86_64) GeoBot/2.0",
    "AlgeriaTransitCollector/1.0 (contact@example.com)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSMDataCollector/1.0",
]

WILAYA_BY_ID: dict[int, dict[str, Any]] = {
    1: {"name_en": "Adrar", "name_fr": "Adrar", "lat": 27.87, "lng": -0.29},
    2: {"name_en": "Chlef", "name_fr": "Chlef", "lat": 36.16, "lng": 1.33},
    3: {"name_en": "Laghouat", "name_fr": "Laghouat", "lat": 33.80, "lng": 2.88},
    4: {"name_en": "Oum El Bouaghi", "name_fr": "Oum El Bouaghi", "lat": 35.87, "lng": 7.12},
    5: {"name_en": "Batna", "name_fr": "Batna", "lat": 35.55, "lng": 6.17},
    6: {"name_en": "Bejaia", "name_fr": "Béjaïa", "lat": 36.75, "lng": 5.06},
    7: {"name_en": "Biskra", "name_fr": "Biskra", "lat": 34.85, "lng": 5.73},
    8: {"name_en": "Bechar", "name_fr": "Béchar", "lat": 31.62, "lng": -2.22},
    9: {"name_en": "Blida", "name_fr": "Blida", "lat": 36.47, "lng": 2.83},
    10: {"name_en": "Bouira", "name_fr": "Bouira", "lat": 36.37, "lng": 3.90},
    11: {"name_en": "Tamanrasset", "name_fr": "Tamanrasset", "lat": 22.79, "lng": 5.52},
    12: {"name_en": "Tebessa", "name_fr": "Tébessa", "lat": 35.40, "lng": 8.12},
    13: {"name_en": "Tlemcen", "name_fr": "Tlemcen", "lat": 34.88, "lng": -1.32},
    14: {"name_en": "Tiaret", "name_fr": "Tiaret", "lat": 35.37, "lng": 1.32},
    15: {"name_en": "Tizi Ouzou", "name_fr": "Tizi Ouzou", "lat": 36.72, "lng": 4.05},
    16: {"name_en": "Algiers", "name_fr": "Alger", "lat": 36.75, "lng": 3.04},
    17: {"name_en": "Djelfa", "name_fr": "Djelfa", "lat": 34.67, "lng": 3.25},
    18: {"name_en": "Jijel", "name_fr": "Jijel", "lat": 36.82, "lng": 5.77},
    19: {"name_en": "Setif", "name_fr": "Sétif", "lat": 36.19, "lng": 5.41},
    20: {"name_en": "Saida", "name_fr": "Saïda", "lat": 34.83, "lng": 0.15},
    21: {"name_en": "Skikda", "name_fr": "Skikda", "lat": 36.87, "lng": 6.91},
    22: {"name_en": "Sidi Bel Abbes", "name_fr": "Sidi Bel Abbès", "lat": 35.19, "lng": -0.63},
    23: {"name_en": "Annaba", "name_fr": "Annaba", "lat": 36.90, "lng": 7.77},
    24: {"name_en": "Guelma", "name_fr": "Guelma", "lat": 36.46, "lng": 7.43},
    25: {"name_en": "Constantine", "name_fr": "Constantine", "lat": 36.37, "lng": 6.61},
    26: {"name_en": "Medea", "name_fr": "Médéa", "lat": 36.27, "lng": 2.75},
    27: {"name_en": "Mostaganem", "name_fr": "Mostaganem", "lat": 35.93, "lng": 0.09},
    28: {"name_en": "Msila", "name_fr": "M'Sila", "lat": 35.70, "lng": 4.55},
    29: {"name_en": "Mascara", "name_fr": "Mascara", "lat": 35.40, "lng": 0.14},
    30: {"name_en": "Ouargla", "name_fr": "Ouargla", "lat": 31.96, "lng": 5.33},
    31: {"name_en": "Oran", "name_fr": "Oran", "lat": 35.70, "lng": -0.65},
    32: {"name_en": "El Bayadh", "name_fr": "El Bayadh", "lat": 32.76, "lng": 1.02},
    33: {"name_en": "Illizi", "name_fr": "Illizi", "lat": 26.51, "lng": 8.48},
    34: {"name_en": "Bordj Bou Arreridj", "name_fr": "Bordj Bou Arréridj", "lat": 36.07, "lng": 4.76},
    35: {"name_en": "Boumerdes", "name_fr": "Boumerdès", "lat": 36.76, "lng": 3.48},
    36: {"name_en": "El Tarf", "name_fr": "El Tarf", "lat": 36.77, "lng": 8.31},
    37: {"name_en": "Tindouf", "name_fr": "Tindouf", "lat": 27.67, "lng": -8.13},
    38: {"name_en": "Tissemsilt", "name_fr": "Tissemsilt", "lat": 35.61, "lng": 1.81},
    39: {"name_en": "El Oued", "name_fr": "El Oued", "lat": 33.37, "lng": 6.86},
    40: {"name_en": "Khenchela", "name_fr": "Khenchela", "lat": 35.43, "lng": 7.14},
    41: {"name_en": "Souk Ahras", "name_fr": "Souk Ahras", "lat": 36.29, "lng": 7.95},
    42: {"name_en": "Tipaza", "name_fr": "Tipaza", "lat": 36.59, "lng": 2.45},
    43: {"name_en": "Mila", "name_fr": "Mila", "lat": 36.45, "lng": 6.26},
    44: {"name_en": "Ain Defla", "name_fr": "Aïn Defla", "lat": 36.26, "lng": 1.97},
    45: {"name_en": "Naama", "name_fr": "Naâma", "lat": 33.27, "lng": -0.31},
    46: {"name_en": "Ain Temouchent", "name_fr": "Aïn Témouchent", "lat": 35.30, "lng": -1.14},
    47: {"name_en": "Ghardaia", "name_fr": "Ghardaïa", "lat": 32.49, "lng": 3.67},
    48: {"name_en": "Relizane", "name_fr": "Relizane", "lat": 35.74, "lng": 0.56},
    49: {"name_en": "Timimoun", "name_fr": "Timimoun", "lat": 29.26, "lng": 0.23},
    50: {"name_en": "Beni Abbes", "name_fr": "Béni Abbès", "lat": 30.08, "lng": -2.16},
    51: {"name_en": "Ain Salah", "name_fr": "Aïn Salah", "lat": 27.19, "lng": 2.46},
    52: {"name_en": "Ain Guezzam", "name_fr": "Aïn Guezzam", "lat": 19.57, "lng": 5.77},
    53: {"name_en": "Touggourt", "name_fr": "Touggourt", "lat": 33.11, "lng": 6.06},
    54: {"name_en": "Djanet", "name_fr": "Djanet", "lat": 24.55, "lng": 9.48},
    55: {"name_en": "El M'Ghair", "name_fr": "El M'Ghair", "lat": 33.95, "lng": 5.92},
    56: {"name_en": "El Menia", "name_fr": "El Menia", "lat": 30.58, "lng": 2.88},
    57: {"name_en": "Ouled Djellal", "name_fr": "Ouled Djellal", "lat": 34.43, "lng": 5.07},
    58: {"name_en": "Bordj Badji Mokhtar", "name_fr": "Bordj Badji Mokhtar", "lat": 21.33, "lng": 0.95},
    59: {"name_en": "Aflou", "name_fr": "Aflou", "lat": 34.11, "lng": 2.10},
    60: {"name_en": "El Abiodh Sidi Cheikh", "name_fr": "El Abiodh Sidi Cheikh", "lat": 32.90, "lng": 0.54},
    61: {"name_en": "El Aricha", "name_fr": "El Aricha", "lat": 34.22, "lng": -1.26},
    62: {"name_en": "El Kantara", "name_fr": "El Kantara", "lat": 35.19, "lng": 5.67},
    63: {"name_en": "Barika", "name_fr": "Barika", "lat": 35.40, "lng": 5.37},
    64: {"name_en": "Bou Saada", "name_fr": "Bou Saâda", "lat": 35.22, "lng": 4.18},
    65: {"name_en": "Bir El Ater", "name_fr": "Bir El Ater", "lat": 34.75, "lng": 8.06},
    66: {"name_en": "Ksar El Boukhari", "name_fr": "Ksar El Boukhari", "lat": 35.89, "lng": 2.75},
    67: {"name_en": "Ksar Chellala", "name_fr": "Ksar Chellala", "lat": 35.22, "lng": 2.32},
    68: {"name_en": "Ain Oussera", "name_fr": "Aïn Oussera", "lat": 35.45, "lng": 2.90},
    69: {"name_en": "Messaad", "name_fr": "Messaad", "lat": 34.17, "lng": 3.50},
}

WILAYA_BY_NAME: dict[str, int] = {}
for wid, w in WILAYA_BY_ID.items():
    for key in (w["name_en"], w["name_fr"]):
        clean = key.lower().replace("-", " ").replace("'", " ")
        WILAYA_BY_NAME[clean] = wid
    WILAYA_BY_NAME[str(w["name_en"]).lower()] = wid
    if wid == 16:
        WILAYA_BY_NAME["alger"] = 16
        WILAYA_BY_NAME["alger centre"] = 16

WILAYA_CAPITALS: dict[str, int] = {
    "alger": 16, "oran": 31, "constantine": 25, "annaba": 23,
    "batna": 5, "djelfa": 17, "setif": 19, "sidi bel abbes": 22,
    "biskra": 7, "tebessa": 12, "tiaret": 14, "bejaia": 6,
    "tlemcen": 13, "blida": 9, "bouira": 10, "bechar": 8,
    "mostaganem": 27, "skikda": 21, "ouargla": 30, "laghouat": 3,
    "oum el bouaghi": 4, "khenchela": 40, "jijel": 18, "mila": 43,
    "saida": 20, "chlef": 2, "mascara": 29, "medea": 26,
    "guelma": 24, "boumerdes": 35, "ain defla": 44, "ain temouchent": 46,
    "ghardaia": 47, "relizane": 48, "el oued": 39, "tizi ouzou": 15,
    "bordj bou arreridj": 34, "souk ahras": 41, "tissemsilt": 38,
    "el tarf": 36, "tipaza": 42, "tamanrasset": 11, "adrar": 1,
    "illizi": 33, "naama": 45, "msila": 28, "el bayadh": 32,
    "tindouf": 37, "touggourt": 53, "el menia": 56, "djanet": 54,
    "timimoun": 49, "beni abbes": 50, "ain salah": 51, "ain guezzam": 52,
}

SNTF_STATION_CODES: dict[int, dict[str, Any]] = {
    37: {"name": "Alger (Agha)", "name_ar": "محطة الجزائر آغة", "lat": 36.7599, "lng": 3.0605, "wilaya_id": 16},
    305: {"name": "Oran", "name_ar": "محطة وهران", "lat": 35.6939, "lng": -0.6423, "wilaya_id": 31},
    376: {"name": "Sétif", "name_ar": "محطة سطيف", "lat": 36.1908, "lng": 5.4080, "wilaya_id": 19},
    90: {"name": "Béjaïa", "name_ar": "محطة بجاية", "lat": 36.7506, "lng": 5.0778, "wilaya_id": 6},
    126: {"name": "Bouira", "name_ar": "محطة البويرة", "lat": 36.3806, "lng": 3.9050, "wilaya_id": 10},
    251: {"name": "Lakhdaria", "name_ar": "لخضرية", "lat": 36.5625, "lng": 3.4858, "wilaya_id": 10},
    168: {"name": "Chlef", "name_ar": "محطة الشلف", "lat": 36.1644, "lng": 1.3347, "wilaya_id": 2},
    114: {"name": "Aïn Defla", "name_ar": "عين الدفلى", "lat": 36.2633, "lng": 1.9672, "wilaya_id": 44},
    134: {"name": "Boumerdès", "name_ar": "بومرداس", "lat": 36.7572, "lng": 3.4742, "wilaya_id": 35},
    415: {"name": "Thénia", "name_ar": "الثنية", "lat": 36.7289, "lng": 3.5506, "wilaya_id": 35},
    525: {"name": "Sidi Abdallah", "name_ar": "سيدي عبد الله", "lat": 36.7078, "lng": 2.9106, "wilaya_id": 16},
    560: {"name": "Aéroport Houari Boumediene", "name_ar": "مطار هواري بومدين", "lat": 36.6936, "lng": 3.2194, "wilaya_id": 16},
    71: {"name": "Aïn Defla (alt)", "name_ar": "عين الدفلى", "lat": 36.2633, "lng": 1.9672, "wilaya_id": 44},
    182: {"name": "Chlef (alt)", "name_ar": "الشلف", "lat": 36.1644, "lng": 1.3347, "wilaya_id": 2},
    69: {"name": "Béjaïa (alt)", "name_ar": "بجاية", "lat": 36.7506, "lng": 5.0778, "wilaya_id": 6},
    10: {"name": "Blida", "name_ar": "البليدة", "lat": 36.4764, "lng": 2.8275, "wilaya_id": 9},
    25: {"name": "Constantine", "name_ar": "قسنطينة", "lat": 36.3650, "lng": 6.6147, "wilaya_id": 25},
    23: {"name": "Annaba", "name_ar": "عنابة", "lat": 36.9067, "lng": 7.7628, "wilaya_id": 23},
    5: {"name": "Batna", "name_ar": "باتنة", "lat": 35.5544, "lng": 6.1742, "wilaya_id": 5},
    22: {"name": "Sidi Bel Abbès", "name_ar": "سيدي بلعباس", "lat": 35.1944, "lng": -0.6372, "wilaya_id": 22},
    13: {"name": "Tlemcen", "name_ar": "تلمسان", "lat": 34.8772, "lng": -1.3150, "wilaya_id": 13},
    21: {"name": "Skikda", "name_ar": "سكيكدة", "lat": 36.8722, "lng": 6.9097, "wilaya_id": 21},
    27: {"name": "Mostaganem", "name_ar": "مستغانم", "lat": 35.9314, "lng": 0.0892, "wilaya_id": 27},
    30: {"name": "Ouargla", "name_ar": "ورقلة", "lat": 31.9589, "lng": 5.3267, "wilaya_id": 30},
    7: {"name": "Biskra", "name_ar": "بسكرة", "lat": 34.8511, "lng": 5.7300, "wilaya_id": 7},
    9: {"name": "Blida (alt)", "name_ar": "البليدة", "lat": 36.4764, "lng": 2.8275, "wilaya_id": 9},
}

SNTF_PRICING: dict[tuple[int, int], dict[str, Any]] = {
    (37, 305): {"first": 1860, "second": 1360, "duration": "4h49", "from_name": "ALGER (AGHA)", "to_name": "ORAN"},
    (37, 376): {"first": 620, "second": 440, "duration": None, "from_name": "ALGER (AGHA)", "to_name": "SETIF"},
    (37, 251): {"first": 620, "second": 450, "duration": "0h57", "from_name": "ALGER (AGHA)", "to_name": "LAKHDARIA"},
    (37, 134): {"first": 620, "second": 450, "duration": "0h30", "from_name": "ALGER (AGHA)", "to_name": "BOUMERDES"},
    (37, 90): {"first": 1050, "second": 770, "duration": "4h08", "from_name": "ALGER (AGHA)", "to_name": "BEJAIA"},
    (126, 90): {"first": 720, "second": 525, "duration": "2h24", "from_name": "BOUIRA", "to_name": "BEJAIA"},
    (37, 10): {"first": 620, "second": 450, "duration": "0h35", "from_name": "ALGER (AGHA)", "to_name": "BLIDA"},
    (305, 22): {"first": 620, "second": 450, "duration": "1h10", "from_name": "ORAN", "to_name": "SIDI BEL ABBES"},
    (22, 13): {"first": 620, "second": 450, "duration": "1h20", "from_name": "SIDI BEL ABBES", "to_name": "TLEMCEN"},
    (37, 25): {"first": 1050, "second": 770, "duration": "3h45", "from_name": "ALGER (AGHA)", "to_name": "CONSTANTINE"},
    (37, 23): {"first": 1250, "second": 920, "duration": "6h30", "from_name": "ALGER (AGHA)", "to_name": "ANNABA"},
    (25, 23): {"first": 620, "second": 450, "duration": "2h15", "from_name": "CONSTANTINE", "to_name": "ANNABA"},
    (25, 5): {"first": 620, "second": 450, "duration": "1h30", "from_name": "CONSTANTINE", "to_name": "BATNA"},
    (37, 168): {"first": 820, "second": 600, "duration": "2h10", "from_name": "ALGER (AGHA)", "to_name": "CHLEF"},
    (168, 305): {"first": 820, "second": 600, "duration": "2h30", "from_name": "CHLEF", "to_name": "ORAN"},
}

TRAM_CITIES: dict[str, dict[str, Any]] = {
    "Algiers": {
        "code": "ALG", "wilaya_id": 16, "name_fr": "Alger",
        "stations": [
            ("Les Fusillés", 36.7147, 3.1064),
            ("Ruisseau", 36.7725, 3.0556),
            ("Triplet", 36.7700, 3.0594),
            ("Les Ateliers", 36.7672, 3.0642),
            ("Zighoud Youcef", 36.7086, 3.1100),
            ("Garidi", 36.7000, 3.1178),
            ("Mohamed Belouizdad", 36.6936, 3.1247),
            ("Cité Bachdjarah", 36.6844, 3.1339),
            ("El Annasser", 36.6772, 3.1408),
            ("Café Noir", 36.6700, 3.1500),
            ("Frais-Vallon", 36.6644, 3.1558),
            ("Lycée El Mokrani", 36.6583, 3.1633),
            ("Bourdou", 36.6517, 3.1700),
            ("Champ de Manœuvre", 36.6436, 3.1764),
            ("Université Houari Boumediene", 36.6364, 3.1831),
            ("Haï El Djebassa", 36.6294, 3.1900),
            ("Bab Ezzouar", 36.7189, 3.1800),
            ("Cité 5 Juillet", 36.7131, 3.1906),
        ],
    },
    "Oran": {
        "code": "ORA", "wilaya_id": 31, "name_fr": "Oran",
        "stations": [
            ("Haï Sabah (Sénia)", 35.6386, -0.6250),
            ("Université (USTO)", 35.6411, -0.6367),
            ("Cité Palmeraie", 35.6539, -0.6425),
            ("Médina J'dida", 35.6656, -0.6472),
            ("Place 1er Novembre", 35.6800, -0.6433),
            ("Boulanger", 35.6886, -0.6411),
            ("Dar El Beïda (Oran)", 35.6950, -0.6367),
            ("Palais des Expositions", 35.7039, -0.6306),
            ("Les Castors", 35.7125, -0.6275),
            ("Saint Antoine", 35.7189, -0.6244),
            ("Maraval", 35.7269, -0.6214),
            ("Lycée Pasteur", 35.7319, -0.6175),
            ("Citée El Hillal", 35.7367, -0.6139),
            ("Sidi El Bachir", 35.7417, -0.6108),
            ("M'Dina Jdida (Oran)", 35.6989, -0.6344),
        ],
    },
    "Constantine": {
        "code": "CON", "wilaya_id": 25, "name_fr": "Constantine",
        "stations": [
            ("Belle Vue (Constantine)", 36.3389, 6.6056),
            ("Cité Daksi", 36.3481, 6.6425),
            ("Gare de Constantine", 36.3650, 6.6147),
            ("Place de la République", 36.3603, 6.6089),
            ("Cité 20 Août", 36.3444, 6.6164),
        ],
    },
    "Sétif": {
        "code": "SET", "wilaya_id": 19, "name_fr": "Sétif",
        "stations": [
            ("Gare SNTF Sétif", 36.1886, 5.4056),
            ("Cité des Tanneurs", 36.1811, 5.3975),
            ("Ain El Fouara", 36.1792, 5.4097),
            ("Liberté", 36.1731, 5.4200),
            ("Université Ferhat Abbas", 36.1614, 5.4442),
            ("Cité Mechtat", 36.1558, 5.4594),
            ("El Hidhab", 36.1489, 5.4789),
        ],
    },
    "Ouargla": {
        "code": "OUA", "wilaya_id": 30, "name_fr": "Ouargla",
        "stations": [
            ("Gare SNTF Ouargla", 31.9589, 5.3267),
            ("Cité El Djihad", 31.9536, 5.3414),
            ("Ain El Beida", 31.9475, 5.3558),
            ("Cité 1er Novembre", 31.9422, 5.3664),
            ("Université Kasdi Merbah", 31.9372, 5.3769),
        ],
    },
    "Sidi Bel Abbès": {
        "code": "SBA", "wilaya_id": 22, "name_fr": "Sidi Bel Abbès",
        "stations": [
            ("Gare SNTF Sidi Bel Abbès", 35.1944, -0.6372),
            ("Cité El Wiam", 35.1967, -0.6478),
            ("Place de la Révolution", 35.1933, -0.6206),
            ("Cité 1er Novembre (SBA)", 35.1914, -0.6092),
            ("Université Djillali Liabès", 35.1889, -0.5983),
        ],
    },
    "Mostaganem": {
        "code": "MOS", "wilaya_id": 27, "name_fr": "Mostaganem",
        "stations": [
            ("Gare SNTF Mostaganem", 35.9314, 0.0892),
            ("Place de la Mairie", 35.9350, 0.0839),
            ("Kharrouba", 35.9439, 0.0742),
            ("Université Abdelhamid Ibn Badis", 35.9514, 0.0672),
            ("Salamandre", 35.9611, 0.0575),
            ("Mazagran", 35.9728, 0.0467),
        ],
    },
}

METRO_LINE1: list[dict[str, Any]] = [
    {"name": "Place des Martyrs", "lat": 36.7500, "lng": 3.0678},
    {"name": "Ali Boumendjel", "lat": 36.7467, "lng": 3.0722},
    {"name": "Tafourah - Grande Poste", "lat": 36.7442, "lng": 3.0786},
    {"name": "Khelifa Boukhalfa", "lat": 36.7417, "lng": 3.0853},
    {"name": "1er Mai", "lat": 36.7389, "lng": 3.0928},
    {"name": "Aïssat Idir", "lat": 36.7319, "lng": 3.0989},
    {"name": "Hamma", "lat": 36.7264, "lng": 3.1000},
    {"name": "Jardin d'Essai", "lat": 36.7208, "lng": 3.1019},
    {"name": "Les Fusillés", "lat": 36.7150, "lng": 3.1056},
    {"name": "Cité Amirouche", "lat": 36.7078, "lng": 3.1081},
    {"name": "Cité Mer et Soleil", "lat": 36.6997, "lng": 3.1133},
    {"name": "Haï El Badr", "lat": 36.6933, "lng": 3.1189},
    {"name": "Station ATB Bachdjarah", "lat": 36.6856, "lng": 3.1289},
    {"name": "Bachdjarah Centre", "lat": 36.6800, "lng": 3.1369},
    {"name": "El Harrach Centre", "lat": 36.7167, "lng": 3.1367},
    {"name": "El Harrach Gare", "lat": 36.7133, "lng": 3.1422},
]

SOGRAL_STATIONS: dict[str, list[str]] = {
    "Alger": ["Adrar", "Ain Beida", "Ain Safra", "Annaba", "Bechar", "Biskra", "Constantine",
              "Djelfa", "El Bayadh", "El Oued", "H.Messaoud", "Jijel", "Khenchela", "Mecheria",
              "Mila", "Mostaghanem", "Naama", "Oran", "Saida", "Setif", "Skikda", "Souk Ahras",
              "Tebessa", "Touggourt", "Tlemcen"],
    "Oran": ["Adrar", "Alger", "Annaba", "Bechar", "Biskra", "Chlef", "Constantine", "Djelfa",
             "El Bayadh", "El Oued", "Ghardaia", "Mostaganem", "Ouargla", "Relizane", "Saida",
             "Setif", "Sidi Bel Abbes", "Tlemcen", "Tiaret"],
    "Constantine": ["Alger", "Annaba", "Batna", "Biskra", "Djelfa", "El Oued", "Ghardaia",
                    "Jijel", "Khenchela", "Mila", "Oum El Bouaghi", "Setif", "Souk Ahras",
                    "Tebessa", "Touggourt"],
    "Annaba": ["Alger", "Constantine", "El Tarf", "Guelma", "Souk Ahras", "Tebessa"],
    "Tlemcen": ["Adrar", "Ain Beida", "Ain Safra", "Alger", "Annaba", "Bechar", "Biskra",
                "Constantine", "Djelfa", "El Bayadh", "El Oued", "H.Messaoud", "Jijel",
                "Khenchela", "Mecheria", "Mila", "Mostaghanem", "Naama", "Oran", "Saida",
                "Setif", "Skikda", "Souk Ahras", "Tebessa", "Touggourt"],
    "Tebessa": ["Alger", "Annaba", "Bechar", "Chlef", "Constantine", "Djelfa", "El Oued",
                "Ghardaia", "Illizi", "Mostaganem", "Oran", "Ouargla", "Relizane", "Saida",
                "Setif", "Sidi Bel Abbes", "Tlemcen", "Laghouat"],
    "Bouira": ["Alger", "Bejaia", "Tizi Ouzou", "Bordj Bou Arreridj", "Boumerdes", "Rouiba",
               "Sidi Aissa", "Lakhdaria"],
    "Setif": ["Alger", "Annaba", "Batna", "Biskra", "Bordj Bou Arreridj", "Constantine",
              "Djelfa", "Jijel", "Mila", "Oum El Bouaghi", "Skikda", "Souk Ahras"],
    "Bejaia": ["Alger", "Setif", "Tizi Ouzou", "Bouira", "Bordj Bou Arreridj"],
    "Biskra": ["Alger", "Annaba", "Batna", "Constantine", "Djelfa", "El Oued", "Ghardaia",
               "Laghouat", "Mecheria", "Ouargla", "Setif", "Touggourt"],
    "Djelfa": ["Alger", "Biskra", "Constantine", "El Bayadh", "Ghardaia", "Laghouat",
               "Mecheria", "Ouargla", "Saida", "Tiaret"],
    "Ouargla": ["Alger", "Biskra", "Djelfa", "El Oued", "Ghardaia", "Illizi", "Laghouat",
                "Tamanrasset", "Touggourt"],
    "Ghardaia": ["Alger", "Djelfa", "El Menia", "El Oued", "Laghouat", "Ouargla", "Tamanrasset", "Touggourt"],
}

SOGRAL_TERMINAL_COORDS: dict[str, tuple[float, float]] = {
    "Alger": (36.7333, 3.0833),
    "Oran": (35.6889, -0.6442),
    "Constantine": (36.3583, 6.6194),
    "Annaba": (36.9067, 7.7639),
    "Setif": (36.1917, 5.4089),
    "Blida": (36.4764, 2.8256),
    "Chlef": (36.1619, 1.3350),
    "Bejaia": (36.7492, 5.0758),
    "Tizi Ouzou": (36.7150, 4.0475),
    "Batna": (35.5550, 6.1750),
    "Biskra": (34.8528, 5.7306),
    "Skikda": (36.8728, 6.9100),
    "Tlemcen": (34.8767, -1.3156),
    "El Oued": (33.4644, 6.8681),
    "Ouargla": (31.9583, 5.3333),
    "Ghardaia": (32.4883, 3.6717),
    "Laghouat": (33.7956, 2.8742),
    "Tamanrasset": (22.7850, 5.5228),
    "Djelfa": (34.6733, 3.2481),
    "Medea": (36.2672, 2.7531),
    "Mostaganem": (35.9311, 0.0889),
    "Sidi Bel Abbes": (35.1939, -0.6378),
    "Tiaret": (35.3694, 1.3211),
    "Jijel": (36.8194, 5.7714),
    "Bouira": (36.3808, 3.9053),
    "Souk Ahras": (36.2861, 7.9539),
    "El Tarf": (36.7667, 8.3167),
    "Mila": (36.4500, 6.2647),
    "Relizane": (35.7358, 0.5539),
    "Boumerdes": (36.7567, 3.4744),
    "Msila": (35.7050, 4.5417),
    "Saida": (34.8303, 0.1514),
    "Mascara": (35.3986, 0.1431),
    "Boussaada": (35.2747, 4.2058),
    "Khenchela": (35.4286, 7.1494),
    "Bechar": (31.6167, -2.2247),
    "Tebessa": (35.4072, 8.1208),
    "Tissemsilt": (35.6064, 1.8089),
    "Bou Saada": (35.2747, 4.2061),
}

AIRPORTS: list[dict[str, Any]] = [
    {"name": "Aéroport d'Alger (Houari Boumediene)", "name_ar": "مطار الجزائر", "code": "ALG", "lat": 36.6936, "lng": 3.2194, "wilaya_id": 16},
    {"name": "Aéroport d'Oran (Ahmed Ben Bella)", "name_ar": "مطار وهران", "code": "ORN", "lat": 35.6239, "lng": -0.6211, "wilaya_id": 31},
    {"name": "Aéroport de Constantine (Mohamed Boudiaf)", "name_ar": "مطار قسنطينة", "code": "CZL", "lat": 36.2811, "lng": 6.6172, "wilaya_id": 25},
    {"name": "Aéroport d'Annaba (Rabah Bitat)", "name_ar": "مطار عنابة", "code": "AAE", "lat": 36.8228, "lng": 7.8067, "wilaya_id": 23},
    {"name": "Aéroport de Sétif (Aïn Arnat)", "name_ar": "مطار سطيف", "code": "QSF", "lat": 36.1781, "lng": 5.3244, "wilaya_id": 19},
    {"name": "Aéroport de Béjaïa (Soummam)", "name_ar": "مطار بجاية", "code": "BJA", "lat": 36.7114, "lng": 5.0692, "wilaya_id": 6},
    {"name": "Aéroport de Tlemcen (Zenata)", "name_ar": "مطار تلمسان", "code": "TLM", "lat": 35.0167, "lng": -1.4500, "wilaya_id": 13},
    {"name": "Aéroport de Tamanrasset (Aguenar)", "name_ar": "مطار تمنراست", "code": "TMR", "lat": 22.8122, "lng": 5.4508, "wilaya_id": 11},
    {"name": "Aéroport de Ghardaïa (Noumérat)", "name_ar": "مطار غرداية", "code": "GHA", "lat": 32.3864, "lng": 3.7931, "wilaya_id": 47},
    {"name": "Aéroport d'Ouargla (Aïn Beida)", "name_ar": "مطار ورقلة", "code": "OGX", "lat": 31.9219, "lng": 5.4117, "wilaya_id": 30},
    {"name": "Aéroport d'Illizi (Takhamalt)", "name_ar": "مطار إيليزي", "code": "VVZ", "lat": 26.7153, "lng": 8.5581, "wilaya_id": 33},
    {"name": "Aéroport d'El Oued (Guemar)", "name_ar": "مطار الوادي", "code": "ELU", "lat": 33.5114, "lng": 6.7767, "wilaya_id": 39},
    {"name": "Aéroport de Touggourt (Sidi Madhi)", "name_ar": "مطار تقرت", "code": "TGR", "lat": 33.0667, "lng": 6.0831, "wilaya_id": 53},
    {"name": "Aéroport de Béchar (Boudghene)", "name_ar": "مطار بشار", "code": "CBH", "lat": 31.6442, "lng": -2.2486, "wilaya_id": 8},
    {"name": "Aéroport d'In Salah", "name_ar": "مطار عين صالح", "code": "INZ", "lat": 27.2472, "lng": 2.5119, "wilaya_id": 51},
    {"name": "Aéroport de Djanet (Tiska)", "name_ar": "مطار جانت", "code": "DJG", "lat": 24.2928, "lng": 9.4522, "wilaya_id": 54},
    {"name": "Aéroport de Hassi Messaoud (Oued Irara)", "name_ar": "مطار حاسي مسعود", "code": "HME", "lat": 31.6728, "lng": 6.1403, "wilaya_id": 30},
]

FERRIES: list[dict[str, Any]] = [
    {"name": "Port d'Alger (Ferry)", "name_ar": "ميناء الجزائر", "lat": 36.7556, "lng": 3.0792, "wilaya_id": 16},
    {"name": "Port d'Oran (Ferry)", "name_ar": "ميناء وهران", "lat": 35.7075, "lng": -0.6500, "wilaya_id": 31},
    {"name": "Port d'Annaba (Ferry)", "name_ar": "ميناء عنابة", "lat": 36.9000, "lng": 7.7667, "wilaya_id": 23},
    {"name": "Port de Béjaïa (Ferry)", "name_ar": "ميناء بجاية", "lat": 36.7517, "lng": 5.0806, "wilaya_id": 6},
    {"name": "Port de Skikda (Ferry)", "name_ar": "ميناء سكيكدة", "lat": 36.8744, "lng": 6.9108, "wilaya_id": 21},
    {"name": "Port de Mostaganem (Ferry)", "name_ar": "ميناء مستغانم", "lat": 35.9358, "lng": 0.0878, "wilaya_id": 27},
    {"name": "Port de Ghazaouet (Ferry)", "name_ar": "ميناء الغزوات", "lat": 35.0953, "lng": -1.8625, "wilaya_id": 13},
]

SNTF_LINES: list[dict[str, Any]] = [
    {"name": "Alger → Oran", "line_id": "SNTF_L1", "stations": [37, 71, 168, 48, 305], "subtype": "intercity"},
    {"name": "Alger → Constantine", "line_id": "SNTF_L2", "stations": [37, 126, 376, 25], "subtype": "intercity"},
    {"name": "Alger → Annaba", "line_id": "SNTF_L3", "stations": [37, 126, 376, 25, 23], "subtype": "intercity"},
    {"name": "Alger → Béjaïa", "line_id": "SNTF_L4", "stations": [37, 134, 126, 15, 90], "subtype": "intercity"},
    {"name": "Alger → Blida (Banlieue)", "line_id": "SNTF_B1", "stations": [37, 525, 10], "subtype": "suburban"},
    {"name": "Oran → Tlemcen", "line_id": "SNTF_L5", "stations": [305, 22, 13], "subtype": "intercity"},
    {"name": "Constantine → Annaba", "line_id": "SNTF_L6", "stations": [25, 5, 23], "subtype": "intercity"},
    {"name": "Alger → El Harrach (Banlieue)", "line_id": "SNTF_B2", "stations": [37, 134], "subtype": "suburban"},
]

SETRAM_LINES: list[dict[str, Any]] = [
    {"city": "Algiers", "line_id": "SETRAM_ALG"},
    {"city": "Oran", "line_id": "SETRAM_ORA"},
    {"city": "Constantine", "line_id": "SETRAM_CON"},
    {"city": "Sétif", "line_id": "SETRAM_SET"},
    {"city": "Ouargla", "line_id": "SETRAM_OUA"},
    {"city": "Sidi Bel Abbès", "line_id": "SETRAM_SBA"},
    {"city": "Mostaganem", "line_id": "SETRAM_MOS"},
]


@dataclass
class TransitNode:
    node_id: str
    name: str
    name_ar: str = ""
    name_en: str = ""
    type: str = "train"
    subtype: str = "urban"
    operator: str = "SNTF"
    wilaya_id: int | None = None
    wilaya_name: str = ""
    latitude: float | None = None
    longitude: float | None = None
    osm_data: dict[str, Any] = field(default_factory=dict)
    codes: dict[str, Any] = field(default_factory=dict)
    lines_at_station: list[str] = field(default_factory=list)
    has_parking: bool | None = None
    has_accessibility: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    line_name: str = ""
    line_id: str = ""
    operator: str = "SNTF"
    mode: str = "train"
    subtype: str = "intercity"
    distance_km: float | None = None
    duration_min: int | None = None
    stops_between: int = 0
    direction: str = "forward"
    schedule: list[dict[str, Any]] = field(default_factory=list)
    pricing: dict[str, Any] = field(default_factory=dict)
    frequency_min: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TransitScraperEngine:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.nodes: dict[str, TransitNode] = {}
        self.edges: list[TransitEdge] = []
        self.osm_requests: int = 0
        self.errors: list[str] = []

    def _req(self, url: str, timeout: int = 10) -> dict | list | None:
        import random
        req = urllib.request.Request(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "fr,en;q=0.9"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode()
                return json.loads(content)
        except Exception as e:
            return None

    def _fetch_page(self, url: str, timeout: int = 10) -> str | None:
        import random
        req = urllib.request.Request(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "fr,en;q=0.9"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            return None

    def _slugify(self, name: str) -> str:
        s = name.lower().strip()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        return s.strip("_")

    def _make_node_id(self, prefix: str, name: str, operator: str = "") -> str:
        base = self._slugify(name)
        return f"STATION_{prefix}_{base}".upper()

    def _make_edge_id(self, prefix: str, from_id: str, to_id: str, line_id: str) -> str:
        f_short = from_id.split("_")[-1] if "_" in from_id else from_id
        t_short = to_id.split("_")[-1] if "_" in to_id else to_id
        return f"EDGE_{prefix}_{f_short}_{t_short}_{line_id}".upper()

    def _haversine_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
        return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

    def geocode_station(self, query: str) -> dict[str, float] | None:
        time.sleep(OSM_SLEEP)
        self.osm_requests += 1
        params = urllib.parse.urlencode({"q": f"{query} Algérie", "format": "json", "limit": 1})
        data = self._req(f"{NOMINATIM_SEARCH}?{params}")
        if data and isinstance(data, list) and len(data) > 0:
            return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
        params2 = urllib.parse.urlencode({"q": f"{query} Algeria", "format": "json", "limit": 1})
        data2 = self._req(f"{NOMINATIM_SEARCH}?{params2}")
        if data2 and isinstance(data2, list) and len(data2) > 0:
            return {"lat": float(data2[0]["lat"]), "lng": float(data2[0]["lon"])}
        return None

    def _wilaya_from_name(self, name: str) -> tuple[int, str] | None:
        up = name.upper().strip()
        known: dict[str, int] = {
            "ALGER": 16, "AGHA": 16, "EL HARRACH": 16, "HUSSEIN DEY": 16,
            "ORAN": 31, "CONSTANTINE": 25, "SETIF": 19, "ANNABA": 23,
            "BATNA": 5, "BEJAIA": 6, "BISKRA": 7, "BLIDA": 9,
            "BOUIRA": 10, "CHLEF": 2, "DJELFA": 17, "GUELMA": 24,
            "JIJEL": 18, "KHENCHELA": 40, "MASCARA": 29, "MEDEA": 26,
            "MILA": 43, "MOSTAGANEM": 27, "MSILA": 28, "OUARGLA": 30,
            "RELIZANE": 48, "SAIDA": 20, "SKIKDA": 21, "SOUK AHRAS": 41,
            "TEBESSA": 12, "TIARET": 14, "TIZI OUZOU": 15, "TLEMCEN": 13,
            "BOUMERDES": 35, "AIN DEFLA": 44, "TIPAZA": 42,
            "BECHAR": 8, "EL OUED": 39, "GHARDAIA": 47, "LAGHOUAT": 3,
            "TAMANRASSET": 11, "ADRAR": 1, "ILLIZI": 33, "NAAMA": 45,
            "TINDOUF": 37, "EL BAYADH": 32, "BBA": 34,
        }
        for k, v in known.items():
            if k in up:
                return v, WILAYA_BY_ID[v]["name_en"]
        return None

    def add_or_update_node(self, node: TransitNode) -> str:
        key = node.node_id
        if key in self.nodes:
            existing = self.nodes[key]
            if node.latitude is not None and existing.latitude is None:
                existing.latitude = node.latitude
                existing.longitude = node.longitude
            if node.wilaya_id is not None and existing.wilaya_id is None:
                existing.wilaya_id = node.wilaya_id
                existing.wilaya_name = node.wilaya_name
            for src_line in node.lines_at_station:
                if src_line not in existing.lines_at_station:
                    existing.lines_at_station.append(src_line)
            if node.metadata:
                existing.metadata.update(node.metadata)
            return existing.node_id
        self.nodes[key] = node
        return key

    # ── SOURCE 1: SETRAM Tramways ──────────────────────────────────
    def scrape_setram(self):
        print("  [SETRAM] Harvesting tramway data...")
        for city_name, city_data in TRAM_CITIES.items():
            line_id = f"SETRAM_{city_data['code']}"
            stns = []
            for sname, slat, slng in city_data["stations"]:
                nid = self._make_node_id("TRAM", sname, "SETRAM")
                w = self._wilaya_from_name(sname) or (city_data["wilaya_id"], WILAYA_BY_ID[city_data["wilaya_id"]]["name_en"])
                node = TransitNode(
                    node_id=nid,
                    name=sname,
                    type="tram",
                    subtype="urban",
                    operator="SETRAM",
                    wilaya_id=w[0],
                    wilaya_name=w[1],
                    latitude=slat,
                    longitude=slng,
                    lines_at_station=[f"Tramway de {city_name}"],
                    metadata={"city": city_name, "city_code": city_data["code"], "line_id": line_id},
                )
                self.add_or_update_node(node)
                stns.append(nid)

            for i in range(len(stns) - 1):
                from_node = self.nodes[stns[i]]
                to_node = self.nodes[stns[i + 1]]
                dist = self._haversine_km(from_node.latitude, from_node.longitude,
                                          to_node.latitude, to_node.longitude)
                dur = max(1, round(dist / 20 * 60))
                eid = self._make_edge_id("SETRAM", stns[i], stns[i + 1], line_id)
                self.edges.append(TransitEdge(
                    edge_id=eid,
                    from_node_id=stns[i],
                    to_node_id=stns[i + 1],
                    line_name=f"Tramway de {city_name}",
                    line_id=line_id,
                    operator="SETRAM",
                    mode="tram",
                    subtype="urban",
                    distance_km=dist,
                    duration_min=dur,
                    stops_between=0,
                    direction="forward",
                    frequency_min=5,
                ))
                rev_eid = self._make_edge_id("SETRAM", stns[i + 1], stns[i], line_id)
                self.edges.append(TransitEdge(
                    edge_id=rev_eid,
                    from_node_id=stns[i + 1],
                    to_node_id=stns[i],
                    line_name=f"Tramway de {city_name}",
                    line_id=line_id,
                    operator="SETRAM",
                    mode="tram",
                    subtype="urban",
                    distance_km=dist,
                    duration_min=dur,
                    stops_between=0,
                    direction="backward",
                    frequency_min=5,
                ))
        print(f"    -> {sum(len(v['stations']) for v in TRAM_CITIES.values())} tram stations")

    # ── SOURCE 2: SEMA Metro ───────────────────────────────────────
    def scrape_metro(self):
        print("  [SEMA] Harvesting Algiers Metro data...")
        line_id = "SEMA_L1"
        stns = []
        for s in METRO_LINE1:
            nid = self._make_node_id("METRO", s["name"], "SEMA")
            node = TransitNode(
                node_id=nid,
                name=s["name"],
                name_ar="",
                name_en=s["name"],
                type="metro",
                subtype="urban",
                operator="SEMA",
                wilaya_id=16,
                wilaya_name="Algiers",
                latitude=s["lat"],
                longitude=s["lng"],
                lines_at_station=["Métro d'Alger Ligne 1"],
                metadata={"line": "Ligne 1", "city": "Algiers"},
            )
            self.add_or_update_node(node)
            stns.append(nid)

        for i in range(len(stns) - 1):
            fn = self.nodes[stns[i]]
            tn = self.nodes[stns[i + 1]]
            dist = self._haversine_km(fn.latitude, fn.longitude, tn.latitude, tn.longitude)
            dur = max(1, round(dist / 35 * 60))
            eid = self._make_edge_id("SEMA", stns[i], stns[i + 1], line_id)
            self.edges.append(TransitEdge(
                edge_id=eid, from_node_id=stns[i], to_node_id=stns[i + 1],
                line_name="Métro d'Alger Ligne 1", line_id=line_id,
                operator="SEMA", mode="metro", subtype="urban",
                distance_km=dist, duration_min=dur, stops_between=0,
                direction="forward", frequency_min=3,
                schedule=[{"departure": "05:00", "arrival": "23:00", "train_num": "M1", "days": "daily"}],
            ))
            rev_eid = self._make_edge_id("SEMA", stns[i + 1], stns[i], line_id)
            self.edges.append(TransitEdge(
                edge_id=rev_eid, from_node_id=stns[i + 1], to_node_id=stns[i],
                line_name="Métro d'Alger Ligne 1", line_id=line_id,
                operator="SEMA", mode="metro", subtype="urban",
                distance_km=dist, duration_min=dur, stops_between=0,
                direction="backward", frequency_min=3,
            ))
        print(f"    -> {len(METRO_LINE1)} metro stations")

    # ── SOURCE 3: SNTF Trains ──────────────────────────────────────
    def scrape_sntf(self):
        print("  [SNTF] Harvesting train data...")

        all_codes: dict[int, dict[str, Any]] = {}
        try:
            data = self._req("https://scrapntf.onrender.com/getAllStations/", timeout=8)
            if data and isinstance(data, list):
                for s in data:
                    c = int(s.get("id", 0))
                    if c:
                        all_codes[c] = {
                            "name": s.get("name", f"Station {c}"),
                            "lat": s.get("lat"),
                            "lng": s.get("lng"),
                        }
                print(f"    -> API: {len(all_codes)} stations from scrapntf")
            else:
                all_codes = dict(SNTF_STATION_CODES)
                print(f"    -> API unavailable, using {len(all_codes)} hardcoded stations")
        except Exception:
            all_codes = dict(SNTF_STATION_CODES)
            print(f"    -> API error, using {len(all_codes)} hardcoded stations")

        combined: dict[int, dict[str, Any]] = {}
        for k, v in SNTF_STATION_CODES.items():
            combined[k] = dict(v)
        for k, v in all_codes.items():
            if k not in combined:
                combined[k] = dict(v)
            else:
                if v.get("lat") and combined[k].get("lat") is None:
                    combined[k]["lat"] = v["lat"]
                    combined[k]["lng"] = v["lng"]

        stn_ids: dict[int, str] = {}
        for code, info in combined.items():
            name = info.get("name", f"SNTF Station {code}")
            nid = self._make_node_id("SNTF", name, "SNTF")
            w = self._wilaya_from_name(name)
            lat = info.get("lat")
            lng = info.get("lng")
            stn_ids[code] = nid
            node = TransitNode(
                node_id=nid, name=name, type="train",
                subtype="intercity", operator="SNTF",
                wilaya_id=w[0] if w else info.get("wilaya_id"),
                wilaya_name=w[1] if w else "",
                latitude=lat, longitude=lng,
                codes={"sntf": code, "uic": None, "scrapntf": code},
                metadata={"station_code": code, "source": "sntf"},
            )
            self.add_or_update_node(node)

        for line in SNTF_LINES:
            codes_on_line = line["stations"]
            stns_on_line = [stn_ids.get(c) for c in codes_on_line if c in stn_ids]
            for i in range(len(stns_on_line) - 1):
                fn = stns_on_line[i]
                tn = stns_on_line[i + 1]
                if not fn or not tn:
                    continue
                pitch = (codes_on_line[i], codes_on_line[i + 1])
                pricing = SNTF_PRICING.get(pitch, {})
                from_n = self.nodes.get(fn)
                to_n = self.nodes.get(tn)
                dist = None
                if from_n and to_n and from_n.latitude and to_n.latitude:
                    dist = self._haversine_km(from_n.latitude, from_n.longitude, to_n.latitude, to_n.longitude)

                dur = None
                raw_dur = pricing.get("duration")
                if raw_dur and isinstance(raw_dur, str) and "h" in raw_dur:
                    parts = raw_dur.replace("h", ":").split(":")
                    try:
                        dur = int(parts[0]) * 60 + int(parts[1])
                    except (ValueError, IndexError):
                        dur = None
                if dur is None and dist:
                    speed = 80 if line["subtype"] == "intercity" else 60
                    dur = max(1, round(dist / speed * 60))

                eid = self._make_edge_id("SNTF", fn, tn, line["line_id"])
                self.edges.append(TransitEdge(
                    edge_id=eid, from_node_id=fn, to_node_id=tn,
                    line_name=line["name"], line_id=line["line_id"],
                    operator="SNTF", mode="train", subtype=line["subtype"],
                    distance_km=dist, duration_min=dur, stops_between=0,
                    direction="forward",
                    pricing={"first_class": pricing.get("first"), "second_class": pricing.get("second")},
                    schedule=[{"departure": "06:00", "arrival": "23:00", "train_num": line["line_id"], "days": "daily"}],
                ))
        print(f"    -> {len(combined)} stations, {len(SNTF_LINES)} lines")

    # ── SOURCE 4: SOGRAL Buses ─────────────────────────────────────
    def scrape_sogral(self):
        print("  [SOGRAL] Harvesting bus data...")
        terminal_nodes: dict[str, str] = {}

        for city_name, city_coords in SOGRAL_TERMINAL_COORDS.items():
            nid = self._make_node_id("BUS", f"{city_name} SOGRAL", "SOGRAL")
            w = self._wilaya_from_name(city_name)
            node = TransitNode(
                node_id=nid,
                name=f"Gare Routière de {city_name}",
                type="bus",
                subtype="intercity",
                operator="SOGRAL",
                wilaya_id=w[0] if w else None,
                wilaya_name=w[1] if w else "",
                latitude=city_coords[0],
                longitude=city_coords[1],
                lines_at_station=[],
                metadata={"city": city_name, "source": "sogral"},
            )
            self.add_or_update_node(node)
            terminal_nodes[city_name] = nid

        edge_num = 0
        for origin, destinations in SOGRAL_STATIONS.items():
            if origin not in terminal_nodes:
                continue
            from_nid = terminal_nodes[origin]
            from_node = self.nodes.get(from_nid)
            for dest in destinations:
                if dest not in terminal_nodes:
                    dest_slug = self._slugify(dest)
                    dest_nid = self._make_node_id("BUS", f"{dest} SOGRAL", "SOGRAL")
                    w = self._wilaya_from_name(dest)
                    node = TransitNode(
                        node_id=dest_nid,
                        name=f"Gare Routière de {dest}",
                        type="bus", subtype="intercity", operator="SOGRAL",
                        wilaya_id=w[0] if w else None,
                        wilaya_name=w[1] if w else "",
                        latitude=None, longitude=None,
                        metadata={"city": dest, "source": "sogral"},
                    )
                    self.add_or_update_node(node)
                    terminal_nodes[dest] = dest_nid
                    dest_node = self.nodes.get(dest_nid)
                else:
                    dest_nid = terminal_nodes[dest]
                    dest_node = self.nodes.get(dest_nid)

                if not dest_node:
                    continue

                dist = None
                if from_node and from_node.latitude and dest_node and dest_node.latitude:
                    dist = self._haversine_km(from_node.latitude, from_node.longitude,
                                              dest_node.latitude, dest_node.longitude)
                dur = round(dist / 60 * 60) if dist else None

                edge_num += 1
                lid = f"SOGRAL_L{edge_num}"
                eid = self._make_edge_id("SOGRAL", from_nid, dest_nid, lid)
                self.edges.append(TransitEdge(
                    edge_id=eid, from_node_id=from_nid, to_node_id=dest_nid,
                    line_name=f"{origin} → {dest}", line_id=lid,
                    operator="SOGRAL", mode="bus", subtype="intercity",
                    distance_km=dist, duration_min=dur,
                    stops_between=0, direction="forward",
                ))
        print(f"    -> {len(SOGRAL_TERMINAL_COORDS)} bus terminals")

    # ── Airports ────────────────────────────────────────────────────
    def scrape_airports(self):
        print("  [EGSA] Harvesting airport data...")
        for apt in AIRPORTS:
            nid = self._make_node_id("AIRPORT", apt["name"], "EGSA")
            w = self._wilaya_from_name(apt["name"]) or (apt["wilaya_id"], WILAYA_BY_ID[apt["wilaya_id"]]["name_en"])
            node = TransitNode(
                node_id=nid,
                name=apt["name"],
                name_ar=apt.get("name_ar", ""),
                name_en=apt["name"],
                type="airport",
                subtype="intercity",
                operator="EGSA",
                wilaya_id=w[0] if w else apt["wilaya_id"],
                wilaya_name=w[1] if w else "",
                latitude=apt["lat"],
                longitude=apt["lng"],
                codes={"iata": apt.get("code")},
                metadata={"source": "airport_data"},
            )
            self.add_or_update_node(node)
        print(f"    -> {len(AIRPORTS)} airports")

    # ── Ferries ─────────────────────────────────────────────────────
    def scrape_ferries(self):
        print("  [ENTV] Harvesting ferry data...")
        for ferry in FERRIES:
            nid = self._make_node_id("FERRY", ferry["name"], "ENTV")
            w = self._wilaya_from_name(ferry["name"]) or (ferry["wilaya_id"], WILAYA_BY_ID[ferry["wilaya_id"]]["name_en"])
            node = TransitNode(
                node_id=nid,
                name=ferry["name"],
                name_ar=ferry.get("name_ar", ""),
                name_en=ferry["name"],
                type="ferry", subtype="intercity", operator="ENTV",
                wilaya_id=w[0] if w else ferry["wilaya_id"],
                wilaya_name=w[1] if w else "",
                latitude=ferry["lat"], longitude=ferry["lng"],
                metadata={"source": "ferry_data"},
            )
            self.add_or_update_node(node)
        print(f"    -> {len(FERRIES)} ferry ports")

    # ── Geocode missing coordinates ─────────────────────────────────
    def geocode_missing(self):
        to_geocode = [n for n in self.nodes.values() if n.latitude is None]
        if not to_geocode:
            print("  [Geocode] No missing coordinates to resolve")
            return
        print(f"  [Geocode] Resolving {len(to_geocode)} missing coordinates via OSM Nominatim...")
        for node in to_geocode:
            query = node.name.replace("Gare Routière", "bus station").replace("(Ferry)", "port")
            result = self.geocode_station(query)
            if result:
                node.latitude = result["lat"]
                node.longitude = result["lng"]
                rc = self._geocode_reverse(result["lat"], result["lng"])
                if rc and node.wilaya_id is None:
                    node.wilaya_id, node.wilaya_name = rc
                print(f"    ✓ {node.name}: {result['lat']:.4f}, {result['lng']:.4f}")
            else:
                print(f"    ✗ {node.name}: geocode failed")
        print(f"    -> {self.osm_requests} OSM requests made")

    def _geocode_reverse(self, lat: float, lng: float) -> tuple[int, str] | None:
        params = urllib.parse.urlencode({"lat": lat, "lon": lng, "format": "json", "addressdetails": 1, "accept-language": "fr"})
        data = self._req(f"{NOMINATIM_REVERSE}?{params}")
        if not data or not isinstance(data, dict):
            return None
        addr = data.get("address") or {}
        state = (addr.get("state") or "").lower().strip()
        county = (addr.get("county") or "").lower().strip()
        for cand in (state, county):
            if cand in WILAYA_BY_NAME:
                wid = WILAYA_BY_NAME[cand]
                return wid, str(WILAYA_BY_ID[wid]["name_en"])
        for city_key, wid in WILAYA_CAPITALS.items():
            city = (addr.get("city") or addr.get("town") or addr.get("village") or "").lower().strip()
            if city_key in city or city in city_key:
                return wid, str(WILAYA_BY_ID[wid]["name_en"])
        return None

    def match_stations(self):
        name_to_id: dict[str, str] = {}
        for nid, node in self.nodes.items():
            base = node.name.lower().strip()
            base = re.sub(r"[\(\[].*?[\)\]]", "", base).strip()
            name_to_id[base] = nid

        for nid, node in list(self.nodes.items()):
            base = node.name.lower().strip()
            base_clean = re.sub(r"[\(\[].*?[\)\]]", "", base).strip()
            base_clean = re.sub(r"(gare routière|gare|station)\s+de\s+", "", base_clean).strip()
            for other_nid, other_node in self.nodes.items():
                if other_nid == nid:
                    continue
                other_base = other_node.name.lower().strip()
                other_clean = re.sub(r"[\(\[].*?[\)\]]", "", other_base).strip()
                other_clean = re.sub(r"(gare routière|gare|station)\s+de\s+", "", other_clean).strip()
                if base_clean == other_clean and base_clean:
                    for line in other_node.lines_at_station:
                        if line not in node.lines_at_station:
                            node.lines_at_station.append(line)
                    if node.latitude is None and other_node.latitude is not None:
                        node.latitude = other_node.latitude
                        node.longitude = other_node.longitude

    def deduplicate(self):
        seen_names: dict[str, str] = {}
        to_remove: list[str] = []
        for nid, node in self.nodes.items():
            clean = re.sub(r"\s+", " ", node.name.lower().strip())
            clean = re.sub(r"[\(\[].*?[\)\]]", "", clean).strip()
            if clean in seen_names:
                keep_id = seen_names[clean]
                keep = self.nodes[keep_id]
                for line in node.lines_at_station:
                    if line not in keep.lines_at_station:
                        keep.lines_at_station.append(line)
                if node.latitude is not None and keep.latitude is None:
                    keep.latitude = node.latitude
                    keep.longitude = node.longitude
                to_remove.append(nid)
                for edge in self.edges:
                    if edge.from_node_id == nid:
                        edge.from_node_id = keep_id
                    if edge.to_node_id == nid:
                        edge.to_node_id = keep_id
            else:
                seen_names[clean] = nid
        for rid in to_remove:
            self.nodes.pop(rid, None)

    def export(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

        nodes_out = []
        for nid, node in self.nodes.items():
            d = asdict(node)
            d["node_id"] = nid
            nodes_out.append(d)
        nodes_path = self.output_dir / "transit_nodes.json"
        nodes_path.write_text(json.dumps(nodes_out, ensure_ascii=False, indent=2), encoding="utf-8")

        edges_out = [asdict(e) for e in self.edges]
        edges_path = self.output_dir / "transit_edges.json"
        edges_path.write_text(json.dumps(edges_out, ensure_ascii=False, indent=2), encoding="utf-8")

        counts: dict[str, int] = {}
        for n in self.nodes.values():
            counts[n.operator] = counts.get(n.operator, 0) + 1

        print(f"\n{'='*60}")
        print(f"Nodes: {len(nodes_out)}")
        print(f"Edges: {len(edges_out)}")
        print(f"Breakdown by operator:")
        for op, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {op}: {cnt} nodes")
        print(f"OSM Nominatim requests: {self.osm_requests}")
        if self.errors:
            print(f"Errors ({len(self.errors)}):")
            for err in self.errors[:10]:
                print(f"  - {err}")
        print(f"Output: {nodes_path}")
        print(f"Output: {edges_path}")

    def run_all(self):
        self.scrape_setram()
        self.scrape_metro()
        self.scrape_sntf()
        self.scrape_sogral()
        self.scrape_airports()
        self.scrape_ferries()
        self.deduplicate()
        self.match_stations()
        return self


def main():
    parser = argparse.ArgumentParser(description="Algerian Transit Scraper Engine")
    parser.add_argument("--mode", default="all", choices=["all", "sntf", "setram", "metro", "sogral", "airports", "ferries"],
                        help="Which source to scrape")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR),
                        help="Output directory for JSON files")
    parser.add_argument("--geocode", action="store_true", default=True,
                        help="Geocode missing coordinates (default: True)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    engine = TransitScraperEngine(output_dir)

    mode_map = {
        "all": engine.run_all,
        "sntf": lambda: (engine.scrape_sntf(), engine.deduplicate(), engine.match_stations()),
        "setram": lambda: (engine.scrape_setram(), engine.deduplicate(), engine.match_stations()),
        "metro": lambda: (engine.scrape_metro(), engine.deduplicate(), engine.match_stations()),
        "sogral": lambda: (engine.scrape_sogral(), engine.deduplicate(), engine.match_stations()),
        "airports": lambda: (engine.scrape_airports(), engine.deduplicate(), engine.match_stations()),
        "ferries": lambda: (engine.scrape_ferries(), engine.deduplicate(), engine.match_stations()),
    }

    runner = mode_map.get(args.mode, engine.run_all)
    runner()

    if args.geocode:
        engine.geocode_missing()
        engine.match_stations()

    engine.export()


if __name__ == "__main__":
    main()
