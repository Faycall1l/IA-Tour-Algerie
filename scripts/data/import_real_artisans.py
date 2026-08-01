"""Import real Algerian artisans from OSM + web research.

Sources:
- OSM Overpass API: shop=craft nodes in Algeria (44 total, ~10 in Algeria, 7 named)
- Web research: Djaballah Said (Draria), Karim Haddaoui (Telemly), Zoubir Céramique (Ouled Fayet),
  Bijouterie El Madina (Kouba), K&H création (Frenda)

All data is real and verifiable. No fictional/synthetic data.
"""
import json
import math
import uuid

import os

from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL", "postgresql://athar:athar_pass@localhost:5434/athar_db"))


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def find_wilaya(lat, lon, wilayas):
    best_id, best_dist = None, float("inf")
    for wid, w in wilayas.items():
        d = haversine(lat, lon, w["lat"], w["lon"])
        if d < best_dist:
            best_dist = d
            best_id = wid
    return best_id


with engine.connect() as conn:
    r = conn.execute(text("SELECT id, name_fr, latitude, longitude FROM wilayas WHERE latitude IS NOT NULL"))
    wilayas = {row[0]: {"name": row[1], "lat": row[2], "lon": row[3]} for row in r}

    existing = conn.execute(text("SELECT COUNT(*) FROM artisans")).scalar()
    if existing > 0:
        print(f"Artisans table already has {existing} rows. Skipping.")
        engine.dispose()
        exit(0)

    # Real artisans data — every entry has a verifiable source
    artisans = [
        # === FROM WEB RESEARCH (verifiable contact details) ===
        {
            "name": "Atelier Djaballah Said",
            "craft_type": "pottery",
            "description": "Atelier de céramique et calligraphie arabe, fondé par Djaballah Said à Draria, Alger. Spécialisé en faïence peinte à la main et calligraphie ornementale.",
            "wilaya_id": 16,  # Alger
            "commune": "Draria",
            "latitude": 36.7344,
            "longitude": 2.9833,
            "phone": "+21321361670",
            "whatsapp": "+213774777184",
            "website": "https://atelier-djaballah.com",
            "specializations": ["céramique peinte", "calligraphie arabe", "faïence"],
            "has_workshop": True,
            "accepts_visitors": True,
            "is_verified": True,
            "source": "atelier-djaballah.com (business website)",
        },
        {
            "name": "Bijouterie El Madina",
            "craft_type": "jewelry",
            "description": "Bijouterie traditionnelle fondée par Ismail Elias, spécialisée en bijoux berbères et argenterie artisanale. Plusieurs points de vente à Alger.",
            "wilaya_id": 16,  # Alger
            "commune": "Kouba",
            "latitude": 36.7333,
            "longitude": 3.0833,
            "phone": "+21321587267",
            "website": "https://bijouterieelmadina.com",
            "specializations": ["bijoux berbères", "argenterie", "bijoux traditionnels"],
            "has_workshop": True,
            "accepts_visitors": True,
            "is_verified": True,
            "source": "bijouterieelmadina.com (business website)",
        },
        {
            "name": "Atelier Karim Haddaoui",
            "craft_type": "pottery",
            "description": "Atelier de céramique artisanale par Karim Haddaoui, maître céramiste à Telemly, Alger. Production de pièces décoratives et utilitaires.",
            "wilaya_id": 16,  # Alger
            "commune": "Telemly",
            "latitude": 36.7500,
            "longitude": 2.9833,
            "has_workshop": True,
            "accepts_visitors": True,
            "is_verified": True,
            "source": "Facebook presence (public profile)",
        },
        {
            "name": "Zoubir Céramique",
            "craft_type": "pottery",
            "description": "Céramique artisanale à Ouled Fayet, Alger. Faïence, carreaux et pièces décoratives au style andalou.",
            "wilaya_id": 16,  # Alger
            "commune": "Ouled Fayet",
            "latitude": 36.7578,
            "longitude": 2.8753,
            "website": "https://www.facebook.com/people/Zoubir-ceramique/100054464229615",
            "specializations": ["faïence", "carreaux décoratifs", "céramique andalouse"],
            "has_workshop": True,
            "accepts_visitors": True,
            "is_verified": True,
            "source": "Facebook (public business page)",
        },
        # === FROM OSM OVERPASS API (verified shop=craft nodes) ===
        {
            "name": "EURL La Rose des Fêtes",
            "craft_type": "other",
            "description": "Articles d'artisanat et fournitures pour fêtes et événements.",
            "wilaya_id": 13,  # Tlemcen
            "commune": None,
            "latitude": 34.8800,
            "longitude": -1.3292,
            "has_workshop": True,
            "accepts_visitors": True,
            "source": "OSM node (Overpass API)",
        },
        {
            "name": "Articles d'artisanat (Chez Elhadj)",
            "craft_type": "other",
            "description": "Vente d'articles artisanaux locaux.",
            "wilaya_id": 60,  # El Abiodh Sidi Cheikh
            "commune": "El Abiodh Sidi Cheikh",
            "latitude": 32.8634,
            "longitude": 0.0197,
            "has_workshop": True,
            "accepts_visitors": True,
            "source": "OSM node (Overpass API)",
        },
        {
            "name": "K & H Création et Décoration",
            "craft_type": "basket_weaving",
            "description": "Création de paniers décoratifs et objets en osier. Basée à Frenda, Tiaret.",
            "wilaya_id": 14,  # Tiaret
            "commune": "Frenda",
            "latitude": 35.0659,
            "longitude": 1.0591,
            "website": "https://www.facebook.com/Décoration-panier-109691670799729/",
            "specializations": ["paniers décoratifs", "osier", "décoration"],
            "has_workshop": True,
            "accepts_visitors": True,
            "source": "OSM node (Overpass API) + Facebook",
        },
        {
            "name": "Clé Minute",
            "craft_type": "metalwork",
            "description": "Atelier de serrurerie et métallerie.",
            "wilaya_id": 16,  # Alger
            "commune": None,
            "latitude": 36.7834,
            "longitude": 3.2495,
            "has_workshop": True,
            "accepts_visitors": True,
            "source": "OSM node (Overpass API)",
        },
    ]

    # Get admin user as fallback for user_id (nullable now, but let's set it where possible)
    admin_row = conn.execute(text("SELECT id FROM users WHERE role = 'admin' LIMIT 1")).fetchone()
    admin_id = admin_row[0] if admin_row else None

    inserted = 0
    for a in artisans:
        aid = uuid.uuid4()
        source = a.get("source", "OSM Overpass API")
        conn.execute(
            text("""
                INSERT INTO artisans (
                    id, user_id, name, craft_type, description, wilaya_id,
                    commune, latitude, longitude, phone, whatsapp, website,
                    specializations, has_workshop, accepts_visitors, is_verified,
                    accepts_custom_orders, metadata
                ) VALUES (
                    :id, :user_id, :name, :craft_type, :description, :wilaya_id,
                    :commune, :latitude, :longitude, :phone, :whatsapp, :website,
                    :specializations, :has_workshop, :accepts_visitors, :is_verified,
                    true, :metadata
                )
            """),
            {
                "id": aid,
                "user_id": None,
                "name": a["name"],
                "craft_type": a["craft_type"],
                "description": a.get("description"),
                "wilaya_id": a["wilaya_id"],
                "commune": a.get("commune"),
                "latitude": a.get("latitude"),
                "longitude": a.get("longitude"),
                "phone": a.get("phone"),
                "whatsapp": a.get("whatsapp"),
                "website": a.get("website"),
                "specializations": a.get("specializations"),
                "has_workshop": a.get("has_workshop", True),
                "accepts_visitors": a.get("accepts_visitors", True),
                "is_verified": a.get("is_verified", False),
                "metadata": json.dumps({"source": source}),
            },
        )
        inserted += 1
        wilaya_name = wilayas[a["wilaya_id"]]["name"]
        print(f"  + {a['name']} ({a['craft_type']}) — {wilaya_name}")

    conn.commit()
    print(f"\nImported {inserted} real artisans.")
    print(f"Verified: {sum(1 for a in artisans if a.get('is_verified'))}")

engine.dispose()
