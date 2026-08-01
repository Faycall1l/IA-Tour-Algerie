#!/usr/bin/env python3
"""Add experiences for wilayas that currently have none."""

import os
import sys

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

ADDITIONS = [
    # ── Adrar (1) ──
    ("tour", "Découverte d'Adrar et du Touat", 1,
     "Visite des oasis du Touat, ksour anciens et foggaras. Découverte de l'architecture en brique de terre crue.",
     "Adrar Centre", 27.87, -0.29, 2500, 5.0, 12, "fr",
     ["Guide", "Transport", "Eau"], ["Chapeau", "Crème solaire"]),
    ("cultural", "Les oasis de Timimoun - la rouge", 49,
     "Promenade dans les palmeraies, visite du vieux ksar rouge. Découverte de l'artisanat local et du henné.",
     "Timimoun", 29.26, 0.23, 3000, 4.0, 10, "fr",
     ["Guide", "Thé", "Dattes"], ["Appareil photo"]),

    # ── Chlef (2) ──
    ("tour", "Chlef antique - Ténès et les ruines romaines", 2,
     "Visite de l'antique cité de Ténès, mosquée Sidi Moussa, ruines romaines de la région.",
     "Ténès, Chlef", 36.51, 1.30, 1500, 4.0, 15, "fr",
     ["Guide", "Eau"], ["Appareil photo"]),

    # ── Laghouat (3) ──
    ("tour", "Laghouat - la porte du désert", 3,
     "Découverte de la vieille ville, mosquée Sidi El Hadj Aïssa, palmeraie et oasis de la vallée du M'zi.",
     "Laghouat Centre", 33.80, 2.88, 1200, 3.0, 15, "fr",
     ["Guide", "Eau"], ["Chapeau"]),

    # ── Oum El Bouaghi (4) ──
    ("tour", "Ruines romaines de Tazoult et bordj d'Oum El Bouaghi", 4,
     "Visite des vestiges romains et du bordj ottoman. Histoire de la région des Hauts-Plateaux.",
     "Oum El Bouaghi Centre", 35.87, 7.12, 1000, 3.0, 15, "fr",
     ["Guide"], ["Appareil photo"]),

    # ── Bouira (10) ──
    ("hiking", "Randonnée dans le massif du Djurdjura", 10,
     "Trek dans les forêts de cèdres et chênes du versant sud du Djurdjura. Lacs et points de vue.",
     "Bouira Centre", 36.37, 3.90, 1500, 5.0, 12, "fr",
     ["Guide", "Eau", "Pique-nique"], ["Chaussures de randonnée", "Veste"]),

    # ── Tiaret (14) ──
    ("tour", "Tiaret - ville des cèdres et des cavaliers", 14,
     "Visite des grottes préhistoriques, forêt de cèdres de Taguet, haras national et musée.",
     "Tiaret Centre", 35.37, 1.32, 1200, 4.0, 15, "fr",
     ["Guide", "Eau"], ["Appareil photo"]),

    # ── Djelfa (17) ──
    ("tour", "Djelfa et les gravures rupestres", 17,
     "Découverte des gravures rupestres de la région. Sites néolithiques de la steppe algérienne.",
     "Djelfa Centre", 34.67, 3.25, 1500, 4.0, 12, "fr",
     ["Guide", "Transport", "Eau"], ["Appareil photo", "Chaussures de marche"]),

    # ── Sidi Bel Abbès (22) ──
    ("tour", "Sidi Bel Abbès - la Légion Étrangère", 22,
     "Visite du Musée de la Légion Étrangère, jardin public, mosquée Sidi Bel Abbès.",
     "Sidi Bel Abbès Centre", 35.19, -0.63, 1000, 3.0, 20, "fr",
     ["Guide"], ["Appareil photo"]),

    # ── Guelma (24) ──
    ("tour", "Guelma romaine - théâtre et monuments", 24,
     "Visite du théâtre romain de Guelma, mosaïques, anciennes cités de la Numidie.",
     "Guelma Centre", 36.46, 7.43, 1000, 3.0, 20, "fr",
     ["Guide", "Billet"], ["Appareil photo"]),

    # ── Médéa (26) ──
    ("hiking", "Randonnée dans l'Atlas tellien à Médéa", 26,
     "Balade en forêt de cèdres et pins. Points de vue sur la Mitidja et l'Atlas. Pique-nique champêtre.",
     "Médéa Centre", 36.27, 2.75, 1000, 4.0, 15, "fr",
     ["Guide", "Eau"], ["Chaussures de marche"]),

    # ── M'Sila (28) ──
    ("tour", "M'Sila - ksour et patrimoine", 28,
     "Visite du vieux ksar de M'Sila, palmeraies de la région, artisanat local.",
     "M'Sila Centre", 35.70, 4.55, 1000, 3.0, 15, "fr",
     ["Guide"], ["Appareil photo"]),

    # ── El Bayadh (32) ──
    ("adventure", "Les steppes d'El Bayadh et le djebel Ksel", 32,
     "Expédition dans les monts des Ksour. Paléontologie, gravures rupestres et paysages de steppe.",
     "El Bayadh Centre", 32.76, 1.02, 3000, 6.0, 8, "fr",
     ["Guide", "Transport 4x4", "Eau", "Pique-nique"], ["Jumelles", "Appareil photo"]),

    # ── Bordj Bou Arréridj (34) ──
    ("cultural", "Bordj Bou Arréridj et l'artisanat du tissage", 34,
     "Rencontre avec les artisans tisserands. Découverte des techniques de tapis traditionnels.",
     "Bordj Bou Arréridj Centre", 36.07, 4.76, 800, 3.0, 12, "fr",
     ["Guide", "Cadeau artisanal"], ["Appareil photo"]),

    # ── Tindouf (37) ──
    ("cultural", "Tindouf et la culture sahraouie", 37,
     "Immersion dans la culture du Sahara occidental. Artisanat, thé, musique traditionnelle.",
     "Tindouf Centre", 27.67, -8.13, 2000, 4.0, 10, "fr",
     ["Guide", "Repas", "Eau"], ["Cadeaux pour l'échange"]),

    # ── Tissemsilt (38) ──
    ("wellness", "Sources thermales de Tissemsilt", 38,
     "Détente aux sources d'eau chaude naturelles. Mini-randonnée dans les collines environnantes.",
     "Tissemsilt Centre", 35.61, 1.81, 1000, 3.0, 15, "fr",
     ["Accès sources"], ["Maillot de bain", "Serviette"]),

    # ── Khenchela (40) ──
    ("hiking", "Massif des Aurès à Khenchela", 40,
     "Randonnée dans les monts des Aurès. Forêts de cèdres, villages chaouis, points de vue spectaculaires.",
     "Khenchela Centre", 35.43, 7.14, 1500, 5.0, 12, "fr",
     ["Guide", "Eau", "Pique-nique"], ["Chaussures de randonnée", "Veste chaude"]),

    # ── Souk Ahras (41) ──
    ("tour", "Souk Ahras - patrie de Saint Augustin", 41,
     "Visite du site antique de Thagaste, musée, forêts de la région. Histoire numide et romaine.",
     "Souk Ahras Centre", 36.29, 7.95, 1000, 3.0, 15, "fr",
     ["Guide", "Eau"], ["Appareil photo"]),

    # ── Mila (43) ──
    ("tour", "Le pont naturel de Mila", 43,
     "Découverte du pont naturel de Gravous, les gorges de l'Oued, vieille ville circulaire de Mila.",
     "Mila Centre", 36.45, 6.26, 1000, 3.0, 15, "fr",
     ["Guide"], ["Appareil photo", "Chaussures de marche"]),

    # ── Aïn Defla (44) ──
    ("wellness", "Sources thermales d'Aïn Defla", 44,
     "Journée bien-être aux thermes d'Hammam Righa. Bains chauds naturels, soins et détente.",
     "Hammam Righa, Aïn Defla", 36.32, 2.10, 2500, 4.0, 20, "fr",
     ["Accès thermes", "Déjeuner"], ["Maillot de bain", "Serviette"]),

    # ── Naâma (45) ──
    ("adventure", "Les monts des Ksour à Naâma", 45,
     "Randonnée dans les monts des Ksour. Visite des anciens greniers fortifiés et oasis de montagne.",
     "Naâma Centre", 33.27, -0.31, 2000, 5.0, 10, "fr",
     ["Guide", "Transport", "Eau"], ["Chaussures de randonnée"]),

    # ── Relizane (48) ──
    ("wellness", "Hammam naturel de Relizane", 48,
     "Bain thermal aux sources chaudes de la région. Journée relaxation et découverte des oliveraies.",
     "Relizane Centre", 35.74, 0.56, 1500, 3.0, 15, "fr",
     ["Accès sources", "Collation"], ["Maillot de bain"]),

    # ── Béni Abbès (50) ──
    ("adventure", "Oasis de Béni Abbès - la perle du Saoura", 50,
     "Découverte des oasis, palmeraies et du grand erg occidental. Nuit en bivouac sous les étoiles.",
     "Béni Abbès", 30.08, -2.16, 5000, 24.0, 8, "fr",
     ["Guide", "Repas", "Campement", "Eau"], ["Sac de couchage", "Lampe frontale"]),

    # ── Aïn Guezzam (52) ──
    ("adventure", "Expédition à Aïn Guezzam - aux portes du Sahara profond", 52,
     "Aventure dans l'extrême sud algérien. Dunes, reg, et vie nomade. Rencontre avec les Touaregs.",
     "Aïn Guezzam", 19.57, 5.77, 15000, 48.0, 6, "fr",
     ["Guide", "4x4", "Tout inclus", "Permis"], ["Du matériel sérieux"]),

    # ── Touggourt (53) ──
    ("cultural", "Touggourt et les oasis du Souf", 53,
     "Visite des palmeraies, des ghouts (cratères de plantation) et de la zaouïa de Sidi Bouâbba.",
     "Touggourt Centre", 33.11, 6.06, 1500, 3.0, 12, "fr",
     ["Guide", "Eau", "Dattes"], ["Chapeau"]),

    # ── El M'Ghair (55) ──
    ("tour", "Les oasis d'El M'Ghair", 55,
     "Promenade dans les palmeraies, découverte de l'irrigation traditionnelle et de l'artisanat local.",
     "El M'Ghair", 33.95, 5.92, 1200, 3.0, 12, "fr",
     ["Guide", "Eau"], ["Chapeau"]),

    # ── El Meniaa (56) ──
    ("adventure", "El Meniaa et le Grand Erg Oriental", 56,
     "Excursion dans les dunes du Grand Erg Oriental. Nuit en bivouac et randonnée chamelière.",
     "El Meniaa", 30.58, 2.88, 6000, 24.0, 8, "fr",
     ["Guide", "Repas", "Campement", "Eau"], ["Sac de couchage", "Crème solaire"]),

    # ── Ouled Djellal (57) ──
    ("tour", "Ouled Djellal et la tradition équestre", 57,
     "Découverte de la culture équestre des Hauts-Plateaux. Fantasia, élevage de chevaux et artisanat.",
     "Ouled Djellal", 34.43, 5.07, 1000, 3.0, 15, "fr",
     ["Guide", "Spectacle équestre"], ["Appareil photo"]),

    # ── Bordj Badji Mokhtar (58) ──
    ("adventure", "Aux confins du Sahara - Bordj Badji Mokhtar", 58,
     "Expédition à la frontière sud. Désert absolu, rencontres nomades et observation du ciel austral.",
     "Bordj Badji Mokhtar", 21.33, 0.95, 20000, 48.0, 4, "fr",
     ["Guide", "4x4", "Tout inclus", "Permis militaire"],
     ["Équipement complet", "Eau (10L minimum)"]),
]


def main():
    print("=== Add experiences for missing wilayas ===\n")

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Get providers
        guide = conn.execute(
            text("SELECT id FROM users WHERE phone = '+213500000003'")
        ).fetchone()
        agency = conn.execute(
            text("SELECT id FROM users WHERE phone = '+213500000002'")
        ).fetchone()
        if not guide or not agency:
            print("ERROR: Provider users not found. Run seed_providers.py first.")
            sys.exit(1)

        existing_wilayas = {
            r[0] for r in conn.execute(text("SELECT id FROM wilayas")).fetchall()
        }

        inserted = 0
        for exp in ADDITIONS:
            cat, title, wid, desc, meeting, lat, lng, price, dur, maxp, lang, incl, bring = exp
            if wid not in existing_wilayas:
                print(f"  SKIP {title[:30]} wilaya {wid} not found")
                continue

            provider = guide if cat in ("hiking", "adventure") else agency

            conn.execute(
                text("""
                    INSERT INTO experiences
                        (id, provider_id, title, category, description, wilaya_id,
                         meeting_point, meeting_point_lat, meeting_point_lng,
                         price_dzd, duration_hours, max_participants,
                         language, included, what_to_bring, status)
                    VALUES
                        (gen_random_uuid(), :p, :t, :cat, :d, :w,
                         :m, :mlat, :mlng,
                         :pr, :du, :mp,
                         :lang, :inc, :br, 'active')
                """),
                {
                    "p": str(provider[0]),
                    "t": title, "cat": cat, "d": desc, "w": wid,
                    "m": meeting, "mlat": lat, "mlng": lng,
                    "pr": price, "du": dur, "mp": maxp,
                    "lang": lang, "inc": incl, "br": bring,
                },
            )
            inserted += 1

    print(f"Inserted {inserted} experiences\nDone!")


if __name__ == "__main__":
    main()
