#!/usr/bin/env python3
"""Seed provider users, profiles, and local agencies.

Creates:
  - 4 provider users (hotel, agency, guide, admin)
  - 3 provider profiles
  - 10 curated local agencies covering key tourism regions
"""

import os

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)

USERS = [
    {
        "phone": "+213500000001",
        "role": "hotel",
        "display_name": "Hôteliers Algérie",
        "language": "fr",
        "is_active": True,
        "is_verified": True,
    },
    {
        "phone": "+213500000002",
        "role": "agency",
        "display_name": "Agence de Voyage",
        "language": "fr",
        "is_active": True,
        "is_verified": True,
    },
    {
        "phone": "+213500000003",
        "role": "guide",
        "display_name": "Guide Touristique",
        "language": "fr",
        "is_active": True,
        "is_verified": True,
    },
    {
        "phone": "+213500000004",
        "role": "admin",
        "display_name": "Administrateur ATHAR",
        "language": "fr",
        "is_active": True,
        "is_verified": True,
    },
]

PROFILES = [
    {
        "phone": "+213500000001",
        "provider_type": "hotel",
        "is_verified": True,
        "property_name": "Hôteliers Algérie",
        "property_type": "hotel",
    },
    {
        "phone": "+213500000002",
        "provider_type": "agency",
        "is_verified": True,
        "company_name": "ATHAR Voyages",
        "registration_number": "AT-2025-001",
        "service_areas": ["Alger", "Oran", "Constantine", "Tamanrasset", "Illizi"],
        "website": "https://athar.dz",
        "team_size": 15,
    },
    {
        "phone": "+213500000003",
        "provider_type": "guide",
        "is_verified": True,
        "experience_years": 8,
        "specializations": ["Randonnée", "Culture", "Désert", "Montagne"],
        "max_group_size": 12,
        "certifications": ["Guide National", "Premiers Secours"],
    },
]

AGENCIES = [
    ("Agence Kabylie Découverte", "AKD-2023-001", 15, "+213771234561", True),
    ("Sahara Touring Co.", "STC-2024-002", 11, "+213782345672", True),
    ("Tassili Voyages", "TV-2022-003", 33, "+213793456783", True),
    ("Alger Médina Tours", "AMT-2024-004", 16, "+213704567894", True),
    ("Oran Events & Travel", "OET-2023-005", 31, "+213715678905", True),
    ("Constantine Culture", "CC-2024-006", 25, "+213726789016", True),
    ("Hoggar Expéditions", "HE-2023-007", 11, "+213737890127", True),
    ("Ghardaïa Tourisme", "GT-2024-008", 47, "+213748901238", True),
    ("Tlemcen Heritage Travel", "THT-2023-009", 13, "+213759012349", True),
    ("Jijel Nature & Plage", "JNP-2024-010", 18, "+213760123450", True),
]


def main():
    print("=== Seed providers, profiles & agencies ===\n")

    engine = create_engine(DATABASE_URL)
    user_ids = {}

    with engine.begin() as conn:
        # Check existing wilayas
        wilayas = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT id, name_fr FROM wilayas")).fetchall()
        }
        print(f"Loaded {len(wilayas)} wilayas")

        # ── USERS ──
        for u in USERS:
            existing = conn.execute(
                text("SELECT id FROM users WHERE phone = :phone"),
                {"phone": u["phone"]},
            ).fetchone()
            if existing:
                user_ids[u["phone"]] = existing[0]
                print(f"  User {u['phone']} already exists: {existing[0]}")
                continue
            row = conn.execute(
                text("""
                    INSERT INTO users
                        (id, phone, role, display_name, language, is_active, is_verified)
                    VALUES
                        (gen_random_uuid(), :phone, :role, :display_name, :language, :is_active, :is_verified)
                    RETURNING id
                """),
                u,
            ).fetchone()
            user_ids[u["phone"]] = row[0]
            print(f"  Created user {u['phone']} ({u['role']}): {row[0]}")

        # ── PROVIDER PROFILES ──
        for p in PROFILES:
            uid = user_ids[p.pop("phone")]
            existing_p = conn.execute(
                text("SELECT id FROM provider_profiles WHERE user_id = :uid"),
                {"uid": uid},
            ).fetchone()
            if existing_p:
                print(f"  Profile for {uid} already exists")
                continue
            p["user_id"] = uid
            cols = list(p.keys())
            vals = ", ".join(f":{c}" for c in cols)
            conn.execute(
                text(f"""
                    INSERT INTO provider_profiles
                        (id, {', '.join(cols)})
                    VALUES
                        (gen_random_uuid(), {vals})
                """),
                p,
            )
            print(f"  Created provider profile for {uid}")

        # ── LOCAL AGENCIES ──
        existing_agencies = {
            r[0]
            for r in conn.execute(
                text("SELECT license_number FROM local_agencies")
            ).fetchall()
        }
        for name, license_no, wilaya_id, phone, verified in AGENCIES:
            if license_no in existing_agencies:
                print(f"  Agency {name} already exists")
                continue
            conn.execute(
                text("""
                    INSERT INTO local_agencies
                        (id, name, license_number, wilaya_id, contact_phone, is_verified)
                    VALUES
                        (gen_random_uuid(), :name, :license, :wilaya, :phone, :verified)
                """),
                {
                    "name": name,
                    "license": license_no,
                    "wilaya": wilaya_id if wilaya_id in wilayas else None,
                    "phone": phone,
                    "verified": verified,
                },
            )
            print(f"  Created agency: {name}")

    print("\nDone!")


if __name__ == "__main__":
    main()
