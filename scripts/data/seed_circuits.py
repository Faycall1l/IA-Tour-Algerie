#!/usr/bin/env python3
"""Seed pre-built tourist circuits (multi-day itineraries) with curated POI stops."""

import uuid
import psycopg2
import json

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

CIRCUITS = [
    {
        "title": "Alger, la Blanche",
        "description": "Découvrez Alger en 3 jours : de la Casbah historique au front de mer moderne, en passant par les musées et les jardins. Un circuit complet pour explorer la capitale algérienne.",
        "duration_days": 3,
        "wilaya_id": 16,
        "category": "city",
        "difficulty": "easy",
        "total_budget_est_dzd": 45000,
        "days": [
            {
                "title": "Casbah et cœur historique",
                "items": [
                    ("morning", "poi", "Casbah"), ("afternoon", "poi", "Palais des Raïs"),
                    ("evening", "restaurant", None),
                ]
            },
            {
                "title": "Alger moderne et musées",
                "items": [
                    ("morning", "poi", "Maqam Echahid"), ("afternoon", "poi", "Musée National du Bardo"),
                    ("afternoon", "poi", "Jardin d'Essai"),
                ]
            },
            {
                "title": "Basilique et promenade côtière",
                "items": [
                    ("morning", "poi", "Notre-Dame d'Afrique"),
                    ("afternoon", "poi", "Basilique Saint-Augustin"),
                    ("evening", "experience", "Dîner dégustation cuisine algéroise"),
                ]
            },
        ]
    },
    {
        "title": "Oran et la côte oranaise",
        "description": "3 jours à Oran pour explorer le fort Santa Cruz, la cathédrale, le front de mer et les plages environnantes. Une immersion dans la capitale de l'ouest algérien.",
        "duration_days": 3,
        "wilaya_id": 31,
        "category": "city",
        "difficulty": "easy",
        "total_budget_est_dzd": 40000,
        "days": [
            {
                "title": "Santa Cruz et centre-ville",
                "items": [
                    ("morning", "poi", "Fort Santa Cruz"), ("afternoon", "poi", "Cathédrale du Sacré-Cœur"),
                    ("evening", "poi", "Front de Mer"),
                ]
            },
            {
                "title": "Culture oranaise",
                "items": [
                    ("morning", "poi", "Musée National Ahmed Zabana"),
                    ("afternoon", "poi", "Théâtre d'Oran"),
                    ("evening", "experience", "Soirée musicale oranaise"),
                ]
            },
            {
                "title": "Plages et nature",
                "items": [
                    ("morning", "poi", "Plage d'Oran"),
                    ("afternoon", "stay", "Hôtel les Andalouses"),
                ]
            },
        ]
    },
    {
        "title": "Constantine et l'Est algérien",
        "description": "4 jours au départ de Constantine à travers l'est algérien : les ponts suspendus, le palais d'Ahmed Bey, puis Annaba et les ruines d'Hippone.",
        "duration_days": 4,
        "wilaya_id": 25,
        "category": "cultural",
        "difficulty": "moderate",
        "total_budget_est_dzd": 65000,
        "days": [
            {
                "title": "Constantine, ville des ponts",
                "items": [
                    ("morning", "poi", "Pont Sidi M'Cid"), ("afternoon", "poi", "Palais d'Ahmed Bey"),
                    ("afternoon", "poi", "Gorges du Rhummel"),
                ]
            },
            {
                "title": "Musées et médersa",
                "items": [
                    ("morning", "poi", "Musée National Cirta"),
                    ("afternoon", "poi", "Mosquée Émir Abdelkader"),
                ]
            },
            {
                "title": "Annaba et Hippone",
                "items": [
                    ("morning", "poi", "Basilique Saint-Augustin"),
                    ("afternoon", "poi", "Ruines d'Hippone"),
                    ("evening", "poi", "Cap de Garde"),
                ]
            },
            {
                "title": "Nature et détente",
                "items": [
                    ("morning", "poi", "Plage d'Annaba"),
                    ("afternoon", "stay", "Hôtel à Annaba"),
                ]
            },
        ]
    },
    {
        "title": "Kabylie authentique",
        "description": "4 jours en Kabylie à travers le massif du Djurdjura, les villages perchés de Tizi Ouzou et la côte de Béjaïa. Randonnée, culture et artisanat.",
        "duration_days": 4,
        "wilaya_id": 15,
        "category": "nature",
        "difficulty": "moderate",
        "total_budget_est_dzd": 55000,
        "days": [
            {
                "title": "Djurdjura et randonnée",
                "items": [
                    ("morning", "poi", "Parc National du Djurdjura"),
                    ("afternoon", "experience", "Randonnée guidée dans le Djurdjura"),
                ]
            },
            {
                "title": "Tizi Ouzou et villages kabyles",
                "items": [
                    ("morning", "poi", "Village de Koukou"),
                    ("afternoon", "poi", "Azazga"),
                ]
            },
            {
                "title": "Béjaïa et la mer",
                "items": [
                    ("morning", "poi", "Yemma Gouraya"),
                    ("afternoon", "poi", "Parc National de Gouraya"),
                ]
            },
            {
                "title": "Plages et artisanat",
                "items": [
                    ("morning", "poi", "Plage de Béjaïa"),
                    ("afternoon", "experience", "Atelier artisanat kabyle"),
                ]
            },
        ]
    },
    {
        "title": "Tlemcen royale",
        "description": "3 jours dans la capitale zianide : mosquées, palais, cascades et parc national. Un voyage dans l'histoire de l'ouest algérien.",
        "duration_days": 3,
        "wilaya_id": 13,
        "category": "cultural",
        "difficulty": "easy",
        "total_budget_est_dzd": 38000,
        "days": [
            {
                "title": "Tlemcen historique",
                "items": [
                    ("morning", "poi", "Mosquée de Sidi Boumediene"),
                    ("afternoon", "poi", "Palais El Mechouar"),
                    ("afternoon", "poi", "Lalla Setti"),
                ]
            },
            {
                "title": "Mansourah et cascades",
                "items": [
                    ("morning", "poi", "Bains de Mansourah"),
                    ("afternoon", "poi", "Cascades d'Oureï"),
                ]
            },
            {
                "title": "Parc National de Tlemcen",
                "items": [
                    ("morning", "poi", "Parc National de Tlemcen"),
                    ("afternoon", "experience", "Randonnée dans le parc national"),
                ]
            },
        ]
    },
    {
        "title": "Sahara magique — Ghardaïa, Tamanrasset, Djanet",
        "description": "7 jours dans le Sahara algérien : la vallée du M'Zab, le Hoggar et le Tassili n'Ajjer. Le grand circuit saharien pour les aventuriers.",
        "duration_days": 7,
        "wilaya_id": 47,
        "category": "adventure",
        "difficulty": "challenging",
        "total_budget_est_dzd": 150000,
        "days": [
            {
                "title": "Arrivée à Ghardaïa",
                "items": [
                    ("morning", "poi", "Vallée du M'Zab"),
                    ("afternoon", "poi", "Ghardaïa"),
                ]
            },
            {
                "title": "Pentapole du M'Zab",
                "items": [
                    ("morning", "poi", "Béni Isguen"),
                    ("afternoon", "poi", "Melika"),
                    ("afternoon", "poi", "El Atteuf"),
                ]
            },
            {
                "title": "Vol vers Tamanrasset",
                "items": [
                    ("morning", "transport", "Vol Ghardaïa → Tamanrasset"),
                    ("afternoon", "poi", "Musée de l'Ahaggar"),
                ]
            },
            {
                "title": "Hoggar et Assekrem",
                "items": [
                    ("morning", "experience", "Trek dans le Hoggar"),
                    ("afternoon", "poi", "Assekrem"),
                    ("evening", "poi", "Coucher de soleil à Assekrem"),
                ]
            },
            {
                "title": "Vol vers Djanet",
                "items": [
                    ("morning", "transport", "Vol Tamanrasset → Djanet"),
                    ("afternoon", "poi", "Tassili n'Ajjer"),
                ]
            },
            {
                "title": "Art rupestre du Tassili",
                "items": [
                    ("morning", "poi", "La Vache Qui Pleure"),
                    ("afternoon", "experience", "Excursion guidée aux gravures rupestres"),
                ]
            },
            {
                "title": "Départ",
                "items": [
                    ("morning", "stay", "Hôtel à Djanet"),
                ]
            },
        ]
    },
    {
        "title": "Route des Aurès — Timgad et Kenchela",
        "description": "4 jours sur la route des Aurès : la cité romaine de Timgad, Lambaesis, les monts du Belezma et les paysages montagneux de Kenchela.",
        "duration_days": 4,
        "wilaya_id": 5,
        "category": "cultural",
        "difficulty": "moderate",
        "total_budget_est_dzd": 45000,
        "days": [
            {
                "title": "Batna et Timgad",
                "items": [
                    ("morning", "poi", "Timgad"),
                    ("afternoon", "poi", "Lambaesis"),
                ]
            },
            {
                "title": "Parc National de Belezma",
                "items": [
                    ("morning", "poi", "Parc National de Belezma"),
                    ("afternoon", "experience", "Randonnée dans les monts du Belezma"),
                ]
            },
            {
                "title": "Kenchela et les Aurès",
                "items": [
                    ("morning", "poi", "Forêt de Kenchela"),
                    ("afternoon", "poi", "Zawiya d'El Hamel"),
                ]
            },
            {
                "title": "Lac et départ",
                "items": [
                    ("morning", "poi", "Lac de Kenchela"),
                ]
            },
        ]
    },
    {
        "title": "Tipaza et la côte ouest d'Alger",
        "description": "2 jours à Tipaza : ruines romaines classées UNESCO, Tombeau de la Chrétienne et Parc National de Chenoua. Idéal pour un week-end.",
        "duration_days": 2,
        "wilaya_id": 42,
        "category": "cultural",
        "difficulty": "easy",
        "total_budget_est_dzd": 25000,
        "days": [
            {
                "title": "Tipaza romaine",
                "items": [
                    ("morning", "poi", "Ruines Romaines de Tipaza"),
                    ("afternoon", "poi", "Tombeau de la Chrétienne"),
                ]
            },
            {
                "title": "Chenoua et plages",
                "items": [
                    ("morning", "poi", "Parc National de Chenoua"),
                    ("afternoon", "poi", "Plage de Tipaza"),
                ]
            },
        ]
    },
    {
        "title": "Sétif et Djemila",
        "description": "2 jours autour de Sétif : le site romain de Djemila (UNESCO), la ville de Sétif et le lac de Ayata.",
        "duration_days": 2,
        "wilaya_id": 19,
        "category": "cultural",
        "difficulty": "easy",
        "total_budget_est_dzd": 20000,
        "days": [
            {
                "title": "Djemila",
                "items": [
                    ("morning", "poi", "Site de Djemila"),
                    ("afternoon", "poi", "Musée de Djemila"),
                ]
            },
            {
                "title": "Sétif et nature",
                "items": [
                    ("morning", "poi", "Mosquée Al Atik"),
                    ("afternoon", "poi", "Lac de Ayata"),
                ]
            },
        ]
    },
    {
        "title": "Tassili n'Ajjer — Immersion préhistorique",
        "description": "5 jours dans le Tassili n'Ajjer classé UNESCO : découverte des gravures rupestres, paysages lunaires et nuits désertiques à Djanet.",
        "duration_days": 5,
        "wilaya_id": 54,
        "category": "adventure",
        "difficulty": "challenging",
        "total_budget_est_dzd": 120000,
        "days": [
            {
                "title": "Arrivée à Djanet",
                "items": [
                    ("afternoon", "poi", "Tassili n'Ajjer"),
                ]
            },
            {
                "title": "Vallée de Tadrart",
                "items": [
                    ("morning", "poi", "Vallée de Tadrart"),
                    ("afternoon", "experience", "Randonnée dans la vallée de Tadrart"),
                ]
            },
            {
                "title": "Gravures rupestres",
                "items": [
                    ("morning", "poi", "Gravures rupestres du Tassili"),
                    ("evening", "experience", "Nuit bivouac dans le désert"),
                ]
            },
            {
                "title": "Exploration du plateau",
                "items": [
                    ("morning", "experience", "Trek sur le plateau du Tassili"),
                    ("afternoon", "poi", "Paysages lunaires du Tassili"),
                ]
            },
            {
                "title": "Retour",
                "items": [
                    ("morning", "poi", "Musée de Djanet"),
                ]
            },
        ]
    },
    {
        "title": "Jijel balnéaire",
        "description": "3 jours sur la côte jijelienne : plages, Parc de Taza, Cap Cavallo et cascades. Pour les amateurs de nature et de farniente.",
        "duration_days": 3,
        "wilaya_id": 18,
        "category": "nature",
        "difficulty": "easy",
        "total_budget_est_dzd": 35000,
        "days": [
            {
                "title": "Cap Cavallo et plages",
                "items": [
                    ("morning", "poi", "Cap Cavallo"),
                    ("afternoon", "poi", "Plage de Jijel"),
                ]
            },
            {
                "title": "Parc de Taza",
                "items": [
                    ("morning", "poi", "Parc de Taza"),
                    ("afternoon", "experience", "Randonnée dans le Parc de Taza"),
                ]
            },
            {
                "title": "Cascades et départ",
                "items": [
                    ("morning", "poi", "Cascade de Ziama"),
                ]
            },
        ]
    },
    {
        "title": "Ghardaïa et la vallée du M'Zab",
        "description": "3 jours dans la vallée du M'Zab, inscrite à l'UNESCO : les cinq ksour, le musée et les oasis. Une immersion dans la culture ibadite.",
        "duration_days": 3,
        "wilaya_id": 47,
        "category": "cultural",
        "difficulty": "easy",
        "total_budget_est_dzd": 40000,
        "days": [
            {
                "title": "Ghardaïa et le musée",
                "items": [
                    ("morning", "poi", "Ghardaïa"),
                    ("afternoon", "poi", "Musée du M'Zab"),
                ]
            },
            {
                "title": "Les cinq ksour",
                "items": [
                    ("morning", "poi", "Béni Isguen"),
                    ("afternoon", "poi", "Melika"),
                    ("afternoon", "poi", "El Atteuf"),
                ]
            },
            {
                "title": "Oasis et artisanat",
                "items": [
                    ("morning", "experience", "Atelier artisanat mozabite"),
                    ("afternoon", "poi", "Palmeraie de Ghardaïa"),
                ]
            },
        ]
    },
    {
        "title": "Oran — Découverte du grand Ouest",
        "description": "Du littoral aux hauts plateaux : une découverte de l'ouest algérien avec ses plages méditerranéennes, ses sites historiques, ses musées, et sa fameuse gastronomie.",
        "duration_days": 4,
        "wilaya_id": 31,
        "category": "city",
        "difficulty": "moderate",
        "total_budget_est_dzd": 55000,
        "days": [
            {
                "title": "Oran historique",
                "items": [
                    ("morning", "poi", "Fort Santa Cruz"),
                    ("afternoon", "poi", "Mosquée du Pacha"),
                ]
            },
            {
                "title": "Culture et gastronomie",
                "items": [
                    ("morning", "poi", "Théâtre d'Oran"),
                    ("afternoon", "experience", "Atelier gastronomie oranaise"),
                ]
            },
            {
                "title": "Côte ouest",
                "items": [
                    ("morning", "poi", "Plage de Mostaganem"),
                    ("afternoon", "stay", "Hôtel à Mostaganem"),
                ]
            },
            {
                "title": "Nature sauvage",
                "items": [
                    ("morning", "poi", "Vallée du Chelif"),
                ]
            },
        ]
    },
    {
        "title": "Biskra et les oasis du Zibans",
        "description": "3 jours dans les oasis du Zibans : Biskra, Tolga et El Kantara. La porte du désert et ses palmeraies de dattes Deglet Nour.",
        "duration_days": 3,
        "wilaya_id": 7,
        "category": "nature",
        "difficulty": "easy",
        "total_budget_est_dzd": 30000,
        "days": [
            {
                "title": "Biskra et ses oasis",
                "items": [
                    ("morning", "poi", "Oasis de Biskra"),
                    ("afternoon", "poi", "Sidi Okba"),
                ]
            },
            {
                "title": "El Kantara",
                "items": [
                    ("morning", "poi", "El Kantara"),
                    ("afternoon", "poi", "Palmeraie d'El Kantara"),
                ]
            },
            {
                "title": "Tolga et les dattes",
                "items": [
                    ("morning", "experience", "Dégustation de dattes Deglet Nour à Tolga"),
                ]
            },
        ]
    },
    {
        "title": "Annaba et El Kala — Nature préservée",
        "description": "3 jours dans le nord-est algérien : la basilique Saint-Augustin, les ruines d'Hippone, le Parc National d'El Kala et les lacs. Une région sauvage et préservée.",
        "duration_days": 3,
        "wilaya_id": 23,
        "category": "nature",
        "difficulty": "moderate",
        "total_budget_est_dzd": 40000,
        "days": [
            {
                "title": "Annaba historique",
                "items": [
                    ("morning", "poi", "Basilique Saint-Augustin"),
                    ("afternoon", "poi", "Ruines d'Hippone"),
                ]
            },
            {
                "title": "Parc National d'El Kala",
                "items": [
                    ("morning", "poi", "Parc National d'El Kala"),
                    ("afternoon", "poi", "Lac Mellah"),
                ]
            },
            {
                "title": "Cap Rosa et plages",
                "items": [
                    ("morning", "poi", "Cap Rosa"),
                    ("afternoon", "poi", "Plage d'El Tarf"),
                ]
            },
        ]
    },
]


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Create circuits table
    cur.execute("""
        SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'circuits')
    """)
    if not cur.fetchone()[0]:
        cur.execute("""
            CREATE TABLE circuits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(200) NOT NULL,
                description TEXT,
                duration_days INTEGER NOT NULL CHECK (duration_days >= 1),
                wilaya_id INTEGER REFERENCES wilayas(id),
                category VARCHAR(50) NOT NULL,
                difficulty VARCHAR(20) NOT NULL DEFAULT 'easy',
                total_distance_km FLOAT,
                total_budget_est_dzd FLOAT,
                photo_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE circuit_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                circuit_id UUID REFERENCES circuits(id) ON DELETE CASCADE NOT NULL,
                day_number INTEGER NOT NULL CHECK (day_number >= 1),
                item_order INTEGER NOT NULL DEFAULT 0,
                time_slot VARCHAR(20) CHECK (time_slot IN ('morning','afternoon','evening')),
                item_type VARCHAR(20) NOT NULL CHECK (item_type IN ('poi','stay','experience','restaurant','transport')),
                item_match_name VARCHAR(300),
                notes TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX ix_circuits_wilaya ON circuits(wilaya_id)")
        cur.execute("CREATE INDEX ix_circuit_items_circuit ON circuit_items(circuit_id)")
        conn.commit()
        print("Created circuits + circuit_items tables\n")

    circuit_count = 0
    item_count = 0

    for c in CIRCUITS:
        cur.execute("""
            INSERT INTO circuits (title, description, duration_days, wilaya_id, category, difficulty, total_budget_est_dzd)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (c["title"], c["description"], c["duration_days"], c["wilaya_id"],
              c["category"], c["difficulty"], c.get("total_budget_est_dzd")))
        circuit_id = cur.fetchone()[0]
        circuit_count += 1

        for day_num, day in enumerate(c["days"], 1):
            day_title = day.get("title", f"Jour {day_num}")
            for order, (time_slot, item_type, match_name) in enumerate(day.get("items", [])):
                cur.execute("""
                    INSERT INTO circuit_items (circuit_id, day_number, item_order, time_slot, item_type, item_match_name,
                                               notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (circuit_id, day_num, order, time_slot, item_type, match_name,
                      f"Jour {day_num} - {day_title}"))
                item_count += 1

        print(f"  [{circuit_count:2d}] {c['title'][:40]:40s} {c['duration_days']}j / {c['category']}")

        conn.commit()

    print(f"\nCircuits created: {circuit_count}")
    print(f"Circuit items: {item_count}")
    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
