#!/usr/bin/env python3
"""Seed curated experiences across Algerian wilayas.

Creates real, well-known activities: tours, hikes, cultural visits, food
experiences, adventure trips, and wellness retreats.
"""

import os
import sys

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

EXPERIENCES = [
    # ── Algiers (16) ──
    ("tour", "Visite guidée de la Casbah d'Alger", 16,
     "Découvrez les ruelles de la mythique Casbah, classée au patrimoine mondial de l'UNESCO. Palais des Raïs, mosquée Ketchaoua, et maisons ottomanes.",
     "Place des Martyrs, Alger Centre", 36.785, 3.064,
     1500, 3.0, 15, "fr", ["Guide", "Entrée monuments", "Eau"],
     ["Chaussures confortables", "Appareil photo"], "tour"),
    ("cultural", "Circuit des musées d'Alger", 16,
     "Visite du Musée Bardo, Musée National des Beaux-Arts et Musée du Moudjahid. Plongez dans l'histoire et l'art algériens.",
     "Musée Bardo, Alger", 36.752, 3.048,
     2000, 5.0, 20, "fr", ["Guide", "Billets d'entrée", "Transport"],
     ["Appareil photo"], "cultural"),
    ("food", "Safari culinaire à Alger", 16,
     "Dégustation des spécialités algéroises : couscous, chakhchoukha, merguez, pâtisseries orientales. Marché et restaurants locaux.",
     "Grande Poste d'Alger", 36.768, 3.057,
     2500, 4.0, 10, "fr", ["Tous les repas", "Thé à la menthe"],
     ["Appétit"], "food"),
    ("tour", "Balade au Jardin d'Essais du Hamma", 16,
     "Explorez l'un des plus beaux jardins botaniques au monde. 58 hectares de verdure au cœur de la capitale.",
     "Jardin d'Essais, Boulevard Mohamed Belouizdad", 36.745, 3.076,
     800, 2.0, 30, "fr", ["Entrée", "Guide"],
     ["Eau", "Chapeau"], "tour"),

    # ── Tamanrasset (11) ──
    ("hiking", "Randonnée au Hoggar - Assekrem", 11,
     "Trek de 3 jours dans le massif du Hoggar. Nuit au sommet de l'Assekrem, coucher de soleil légendaire sur le désert.",
     "Auberge de Jeunesse, Tamanrasset", 22.785, 5.523,
     12000, 48.0, 8, "fr", ["Guide", "Repas", "Tente", "Transport 4x4"],
     ["Sac de couchage", "Vêtements chauds", "Lampe frontale"], "hiking"),
    ("adventure", "Expédition dans le Tassili n'Ajjer", 11,
     "Découverte des peintures rupestres préhistoriques du Tassili. Canon de la Tassili, dunes et oasis perdues.",
     "Aéroport de Tamanrasset", 22.785, 5.523,
     25000, 72.0, 6, "fr", ["Guide", "4x4", "Repas", "Équipement camping"],
     ["Eau (3L min)", "Crème solaire", "Chaussures de randonnée"], "adventure"),
    ("adventure", "Ascension du Mont Tahat", 11,
     "Gravissez le plus haut sommet d'Algérie (3 003m). Vue panoramique sur le Hoggar. Niveau confirmé.",
     "Tamanrasset Centre", 22.785, 5.523,
     15000, 24.0, 6, "fr", ["Guide de haute montagne", "Repas", "Équipement"],
     ["Bonne condition physique", "Vêtements techniques"], "adventure"),

    # ── Illizi / Djanet (33/54) ──
    ("adventure", "Les merveilles du Tassili n'Ajjer", 33,
     "Expédition de 5 jours au cœur du plus grand parc national d'Algérie. Peintures rupestres, arches naturelles et canyons.",
     "Djanet Centre", 24.555, 9.482,
     35000, 120.0, 6, "fr", ["Guide", "4x4", "Camping", "Repas", "Permis parc"],
     ["Eau", "Sac de couchage", "Protection solaire"], "adventure"),
    ("cultural", "Rencontre avec les Touaregs du Tassili", 33,
     "Immersion dans la culture touarègue. Campement traditionnel, thé, artisanat et musique. Nuit sous les étoiles.",
     "Djanet", 24.555, 9.482,
     8000, 24.0, 12, "fr", ["Repas", "Campement", "Artisanat offert"],
     ["Cadeaux pour l'échange"], "cultural"),

    # ── Béjaïa (6) ──
    ("hiking", "Randonnée au Parc National de Gouraya", 6,
     "Sentier côtier avec vue imprenable sur la Méditerranée. Faune : singes magots. Baignade aux criques sauvages.",
     "Entrée du Parc Gouraya", 36.769, 5.103,
     1000, 4.0, 15, "fr", ["Guide", "Eau"],
     ["Chaussures de randonnée", "Maillot de bain", "Casquette"], "hiking"),
    ("tour", "Découverte de la vieille ville de Béjaïa", 6,
     "Souk, port, Casbah et remparts. Histoire de la capitale des Hammadides et de l'émir Abd el-Kader.",
     "Port de Béjaïa", 36.752, 5.075,
     1200, 3.0, 20, "fr", ["Guide", "Eau"],
     ["Appareil photo"], "tour"),

    # ── Jijel (18) ──
    ("tour", "Les grottes merveilleuses de Jijel", 18,
     "Visite des Grottes Merveilleuses, site naturel classé. Stalactites et stalagmites aux couleurs féériques.",
     "Grottes Merveilleuses, Route de Béjaïa", 36.825, 5.767,
     1500, 3.0, 25, "fr", ["Billet d'entrée", "Guide"],
     ["Veste légère", "Appareil photo"], "tour"),
    ("adventure", "Plages et criques de la côte jijelienne", 18,
     "Excursion en bateau le long de la côte. Plages sauvages de Taza, plongée et pique-nique sur une île.",
     "Port de Jijel", 36.822, 5.770,
     3000, 6.0, 12, "fr", ["Bateau", "Repas", "Masque/tuba"],
     ["Maillot de bain", "Crème solaire"], "adventure"),

    # ── Constantine (25) ──
    ("tour", "Circuit des ponts de Constantine", 25,
     "Visite des 7 ponts emblématiques de la ville des ponts suspendus. Pont Sidi M'Cid, pont d'El Kantara, passerelle Mellah.",
     "Pont d'El Kantara, Constantine", 36.367, 6.615,
     1000, 3.0, 20, "fr", ["Guide", "Eau"],
     ["Appareil photo", "Chaussures confortables"], "tour"),
    ("cultural", "Palais du Bey et musées de Constantine", 25,
     "Visite du Palais du Bey, Musée Cirta, Médersa et Mosquée Emir Abdelkader. Art et architecture ottomane.",
     "Palais du Bey, Constantine", 36.365, 6.611,
     1500, 4.0, 15, "fr", ["Guide", "Billets", "Transport"],
     ["Appareil photo"], "cultural"),

    # ── Tlemcen (13) ──
    ("tour", "Tlemcen la musulmane - mosquées et medersa", 13,
     "Mosquée de Sidi Boumediene, Medersa de Tlemcen, Mosquée d'El Mechouar. Art hispano-mauresque exceptionnel.",
     "Place Sidi Boumediene, Mansourah", 34.871, -1.316,
     1000, 4.0, 20, "fr", ["Guide", "Entrées"],
     ["Chaussures confortables"], "tour"),
    ("cultural", "Les grottes de Beni Add et cascades", 13,
     "Découverte des grottes souterraines et cascades de Beni Add. Bain dans les piscines naturelles.",
     "Gare routière de Tlemcen", 34.880, -1.320,
     2000, 5.0, 12, "fr", ["Guide", "Transport", "Eau"],
     ["Maillot de bain", "Serviette", "Chaussures aquatiques"], "adventure"),

    # ── Oran (31) ──
    ("tour", "Oran - histoire et architecture", 31,
     "Fort de Santa Cruz, Chapelle espagnole, Théâtre d'Oran, Place 1er Novembre. Panorama sur la baie d'Oran.",
     "Place 1er Novembre, Oran", 35.704, -0.652,
     1500, 4.0, 20, "fr", ["Guide", "Eau"],
     ["Appareil photo", "Casquette"], "tour"),
    ("cultural", "La musique raï et la culture oranaise", 31,
     "Visite du Palais de la Culture, rencontre avec des musiciens, découverte du patrimoine musical oranais.",
     "Palais de la Culture, Oran", 35.706, -0.648,
     2000, 3.0, 15, "fr", ["Guide", "Spectacle", "Thé"],
     ["Appareil photo"], "cultural"),

    # ── Ghardaïa (47) ──
    ("cultural", "La Vallée du M'zab - cités berbères ibadites", 47,
     "Visite des 5 ksour de la pentapole : Ghardaïa, Beni Isguen, Melika, Bounoura, At Beni. Architecture unique au monde.",
     "Place du Marché, Ghardaïa", 32.488, 3.674,
     2000, 6.0, 12, "fr", ["Guide local", "Eau", "Entrées"],
     ["Tenue modeste", "Appareil photo"], "cultural"),
    ("food", "Atelier cuisine mozabite", 47,
     "Apprenez à cuisiner le pain traditionnel (tamellaqt), le couscous mozabite et les pâtisseries locales.",
     "Maison traditionnelle, Ghardaïa", 32.490, 3.675,
     2500, 4.0, 8, "fr", ["Ingrédients", "Repas", "Recettes"],
     ["Tablier"], "food"),

    # ── Batna (5) ──
    ("tour", "Visite des ruines romaines de Timgad", 5,
     "Pompei d'Afrique. Arc de Trajan, théâtre romain, forum, thermes. Cité romaine la mieux conservée d'Afrique du Nord.",
     "Timgad, 35km de Batna", 35.487, 6.468,
     2000, 4.0, 25, "fr", ["Guide", "Billet", "Transport"],
     ["Eau", "Chapeau", "Appareil photo"], "tour"),
    ("cultural", "Cuisine et traditions des Aurès", 5,
     "Rencontre avec les familles chaouies. Préparation du couscous au beurre, de l'chakhchoukha et du pain traditionnel.",
     "Musée du Moudjahid, Batna", 35.555, 6.175,
     2000, 5.0, 10, "fr", ["Repas complet", "Cadeau artisanal"],
     ["Appétit"], "cultural"),

    # ── Sétif (19) ──
    ("tour", "Djemila - la perle romaine de Sétif", 19,
     "Visite de l'antique Cuicul. Remarquable musée en plein air : forum, temple, baptistère, maisons romaines.",
     "Djemila, 40km de Sétif", 36.321, 5.736,
     2000, 4.0, 25, "fr", ["Guide", "Billet", "Transport"],
     ["Eau", "Chapeau", "Appareil photo"], "tour"),

    # ── Tipaza (42) ──
    ("tour", "Ruines romaines de Tipaza", 42,
     "Site classé UNESCO. Forum, basilique, théâtre romain face à la mer. Le tombeau de la Chrétienne en option.",
     "Entrée du site archéologique, Tipaza", 36.591, 2.443,
     1500, 3.0, 25, "fr", ["Guide", "Billet"],
     ["Appareil photo", "Eau"], "tour"),
    ("tour", "Tombeau de la Chrétienne (Medracen)", 42,
     "Monument funéraire numide impressionnant. Vestige du royaume de Maurétanie. Panorama sur la côte.",
     "Route de Tipaza, 10km", 36.575, 2.558,
     1000, 2.0, 20, "fr", ["Guide", "Billet"],
     ["Chaussures confortables"], "tour"),

    # ── Tizi Ouzou (15) ──
    ("hiking", "Randonnée au Djurdjura - Tikjda", 15,
     "Randonnée en montagne dans le Parc National du Djurdjura. Cèdres, lacs et névés. Sommets à 2 300m.",
     "Station de Tikjda", 36.468, 4.131,
     1500, 6.0, 12, "fr", ["Guide", "Eau"],
     ["Chaussures de randonnée", "Veste chaude", "Pique-nique"], "hiking"),
    ("cultural", "Village kabyle authentique", 15,
     "Visite d'un village kabyle perché. Maisons traditionnelles, grenier collectif, artisanat du bijou et du tapis.",
     "Aït Idour, route de Yakouren", 36.714, 4.124,
     1500, 4.0, 15, "fr", ["Guide", "Eau", "Collation"],
     ["Appareil photo"], "cultural"),

    # ── Blida (9) ──
    ("hiking", "Parc National de Chréa", 9,
     "Randonnée en forêt de cèdres, neige en hiver. Singes magots, gorges de la Chiffa, point de vue sur la Mitidja.",
     "Station de Chréa", 36.428, 2.873,
     1200, 5.0, 15, "fr", ["Guide", "Eau"],
     ["Chaussures de marche", "Veste", "Pique-nique"], "hiking"),

    # ── Biskra (7) ──
    ("tour", "Oasis de Biskra - les Ziban et Sidi Okba", 7,
     "Découverte des oasis de Biskra et de Sidi Okba. Palmeraies, sources thermales et mosquée de Sidi Okba.",
     "Centre-ville de Biskra", 34.850, 5.735,
     1500, 4.0, 15, "fr", ["Guide", "Transport", "Eau"],
     ["Chapeau", "Crème solaire"], "tour"),

    # ── Annaba (23) ──
    ("tour", "Basilique Saint-Augustin et Hippone", 23,
     "Visite de la Basilique Saint-Augustin et des ruines romaines d'Hippone. L'héritage chrétien d'Afrique du Nord.",
     "Basilique Saint-Augustin, Annaba", 36.883, 7.760,
     1500, 3.0, 20, "fr", ["Guide", "Billets"],
     ["Tenue modeste", "Appareil photo"], "tour"),

    # ── Skikda (21) ──
    ("tour", "Skikda - la ville aux jardins", 21,
     "Promenade au port, théâtre romain de Philippeville, jardin public, grottes de Stora.",
     "Port de Skikda", 36.875, 6.905,
     1000, 3.0, 20, "fr", ["Guide"],
     ["Appareil photo"], "tour"),

    # ── Mostaganem (27) ──
    ("wellness", "Thermes et soins à Mostaganem", 27,
     "Journée bien-être aux sources thermales de Mostaganem. Hammam traditionnel et soins aux huiles naturelles.",
     "Centre-ville de Mostaganem", 35.934, 0.089,
     3000, 5.0, 10, "fr", ["Accès thermes", "Déjeuner", "Soins"],
     ["Maillot de bain", "Serviette"], "wellness"),

    # ── Béchar (8) ──
    ("adventure", "Les dunes de Taghit", 8,
     "Randonnée à dos de dromadaire dans les dunes de Taghit. Nuit en bivouac, musique sahraouie et ciel étoilé.",
     "Taghit, 50km de Béchar", 30.420, -2.100,
     8000, 24.0, 10, "fr", ["Guide", "Dromadaire", "Repas", "Campement"],
     ["Sac de couchage", "Lampe", "Vêtements chauds"], "adventure"),

    # ── El Oued (39) ──
    ("cultural", "Souf et oasis d'El Oued", 39,
     "Visite des oasis d'El Oued et de l'architecture traditionnelle des ksour. Artisanat du tapis soufi.",
     "El Oued Centre", 33.370, 6.862,
     1500, 4.0, 15, "fr", ["Guide", "Transport", "Eau"],
     ["Chapeau", "Crème solaire"], "cultural"),

    # ── Djanet (54) ──
    ("adventure", "Trek dans le Tassili - Djanet", 54,
     "3 jours de trek dans le Tassili n'Ajjer. Peintures rupestres de Sefar et Jabbaren. Nuits en refuge.",
     "Djanet", 24.555, 9.482,
     20000, 72.0, 6, "fr", ["Guide", "Repas", "Camping", "Permis"],
     ["Eau", "Sac de couchage", "Chaussures de trek"], "adventure"),

    # ── Tébessa (12) ──
    ("tour", "Tébessa et son temple romain", 12,
     "Visite du temple de Minerve (le mieux conservé d'Afrique), basilique, muraille byzantine.",
     "Temple de Minerve, Tébessa", 35.406, 8.121,
     1000, 3.0, 20, "fr", ["Guide", "Billet"],
     ["Appareil photo"], "tour"),

    # ── Aïn Salah (51) ──
    ("adventure", "Foggara et ksour d'Aïn Salah", 51,
     "Découverte des foggaras (système d'irrigation ancestral), ksour de l'oued, oasis du Tidikelt.",
     "Aïn Salah", 27.194, 2.466,
     5000, 5.0, 8, "fr", ["Guide", "Transport 4x4", "Eau"],
     ["Crème solaire", "Chapeau"], "adventure"),

    # ── El Tarf (36) ──
    ("tour", "Parc National d'El Kala", 36,
     "Réserve de biosphère UNESCO. Lacs, forêts de liège, plages sauvages. Observation d'oiseaux migrateurs.",
     "El Kala", 36.888, 8.443,
     2000, 5.0, 12, "fr", ["Guide", "Eau", "Longue-vue"],
     ["Jumelles", "Appareil photo"], "tour"),

    # ── Saïda (20) ──
    ("wellness", "Forêt des cèdres de Saïda", 20,
     "Randonnée en forêt de cèdres et détente. Pique-nique au milieu des arbres centenaires. Source d'air pur.",
     "Forêt de cèdres, Saïda", 34.840, 0.154,
     1000, 3.0, 15, "fr", ["Guide", "Eau"],
     ["Chaussures de marche", "Pique-nique"], "wellness"),

    # ── Ouargla (30) ──
    ("cultural", "Ksar et palmeraies d'Ouargla", 30,
     "Visite du vieux ksar, des palmeraies et des souks traditionnels. Dégustation de dattes Deglet Nour.",
     "Ouargla Centre", 31.960, 5.338,
     1200, 3.0, 15, "fr", ["Guide", "Dattes"],
     ["Chapeau"], "cultural"),

    # ── Boumerdès (35) ──
    ("wellness", "Plages et détente à Boumerdès", 35,
     "Journée farniente sur les plages de la côte est. Baignade, sports nautiques et déjeuner de poisson grillé.",
     "Cap Djinet, Boumerdès", 36.872, 3.728,
     2000, 5.0, 15, "fr", ["Transport", "Déjeuner"],
     ["Maillot de bain", "Crème solaire", "Serviette"], "wellness"),

    # ── Aïn Témouchent (46) ──
    ("tour", "Plages et vignobles de l'ouest", 46,
     "Découverte des plages sauvages de Sassel et Bouzedjar. Dégustation de vins locaux et d'huile d'olive.",
     "Aïn Témouchent", 35.302, -1.140,
     1500, 5.0, 12, "fr", ["Guide", "Déjeuner", "Dégustation"],
     ["Maillot de bain"], "tour"),

    # ── Mascara (29) ──
    ("tour", "Sur les traces de l'Émir Abd el-Kader", 29,
     "Visite de Mascara, capitale de l'État de l'Émir. Mosquée, palais, musée de l'Émir et campagne environnante.",
     "Mascara Centre", 35.401, 0.140,
     1000, 3.0, 15, "fr", ["Guide"],
     ["Appareil photo"], "tour"),
]

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi", 5: "Batna",
    6: "Béjaïa", 7: "Biskra", 8: "Béchar", 9: "Blida", 10: "Bouira",
    11: "Tamanrasset", 12: "Tébessa", 13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou",
    16: "Alger", 17: "Djelfa", 18: "Jijel", 19: "Sétif", 20: "Saïda",
    21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba", 24: "Guelma", 25: "Constantine",
    26: "Médéa", 27: "Mostaganem", 28: "M'Sila", 29: "Mascara", 30: "Ouargla",
    31: "Oran", 32: "El Bayadh", 33: "Illizi", 34: "Bordj Bou Arréridj",
    35: "Boumerdès", 36: "El Tarf", 37: "Tindouf", 38: "Tissemsilt", 39: "El Oued",
    40: "Khenchela", 41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Aïn Defla",
    45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa", 48: "Relizane",
    49: "Timimoun", 50: "Béni Abbès", 51: "Aïn Salah", 52: "Aïn Guezzam",
    53: "Touggourt", 54: "Djanet", 55: "El M'Ghair", 56: "El Meniaa",
    57: "Ouled Djellal", 58: "Bordj Badji Mokhtar",
}


def main():
    print("=== Seed curated experiences ===\n")

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Get guide & agency providers
        guide_user = conn.execute(
            text("SELECT id FROM users WHERE phone = '+213500000003'")
        ).fetchone()
        agency_user = conn.execute(
            text("SELECT id FROM users WHERE phone = '+213500000002'")
        ).fetchone()

        if not guide_user or not agency_user:
            print("ERROR: Provider users not found. Run seed_providers.py first.")
            sys.exit(1)

        guide_id = guide_user[0]
        agency_id = agency_user[0]

        # Verify wilayas exist
        existing_wilayas = {
            row[0]
            for row in conn.execute(text("SELECT id FROM wilayas")).fetchall()
        }

        # Truncate
        conn.execute(text("DELETE FROM trip_items"))
        conn.execute(text("DELETE FROM bookings"))
        conn.execute(text("TRUNCATE TABLE experiences RESTART IDENTITY CASCADE"))

        inserted = 0
        for exp in EXPERIENCES:
            cat, title, wid, desc, meeting, lat, lng, price, dur, max_p, lang, included, bring, exp_type = exp

            if wid not in existing_wilayas:
                print(f"  SKIP {title[:30]:30s} wilaya {wid} not found")
                continue

            provider = guide_id if exp_type in ("hiking", "adventure") else agency_id

            conn.execute(
                text("""
                    INSERT INTO experiences
                        (id, provider_id, title, category, description, wilaya_id,
                         meeting_point, meeting_point_lat, meeting_point_lng,
                         price_dzd, duration_hours, max_participants,
                         language, included, what_to_bring, status)
                    VALUES
                        (gen_random_uuid(), :provider, :title, :cat, :desc, :wid,
                         :meeting, :mlat, :mlng,
                         :price, :dur, :maxp,
                         :lang, :incl, :bring, 'active')
                """),
                {
                    "provider": str(provider),
                    "title": title,
                    "cat": cat,
                    "desc": desc,
                    "wid": wid,
                    "meeting": meeting,
                    "mlat": lat,
                    "mlng": lng,
                    "price": price,
                    "dur": dur,
                    "maxp": max_p,
                    "lang": lang,
                    "incl": included,
                    "bring": bring,
                },
            )
            inserted += 1

        print(f"Inserted {inserted} experiences")

    print("\nDone!")


if __name__ == "__main__":
    main()
