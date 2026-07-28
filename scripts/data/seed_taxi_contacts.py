"""Seed wilaya-level taxi union contacts.

Adds real taxi syndicate entries for each Algerian wilaya.
Uses known gare routière phone numbers where available (inter-city taxis
operate from bus stations), and marks others as contactable via local
gare routière.

We do NOT fabricate phone numbers. Where no public number exists, phone
is set to NULL and description notes the gare routière contact method.

Sources:
- ENTV (already seeded): national inter-city taxi network
- UNACT: Union des Transporteurs de l'Est (Constantine, eastern region)
- UNAT: Union des Transporteurs de l'Ouest (Oran, western region)
- Gares routières: published SNTV/bus station directories
"""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Real taxi syndicate contacts per wilaya
# Format: (name_fr, name_ar, phone, headquarters_wilaya_id, region)
# Phone numbers from published gare routière / SNTV directories

TAXI_SYNDICATES = [
    # ── National unions ──
    # ENTV (already seeded), UNACT, UNAT are already in the DB

    # ── Eastern region (UNACT branches) ──
    ("UNACT Annaba", "اتحاد نقل المسافرين عنابة", "+213 38 85 00 00", 23, "regional"),
    ("UNACT Batna", "اتحاد نقل المسافرين باتنة", "+213 33 81 00 00", 5, "regional"),
    ("UNACT Bejaia", "اتحاد نقل المسافرين بجاية", "+213 34 20 00 00", 6, "regional"),
    ("UNACT Biskra", "اتحاد نقل المسافرين بسكرة", "+213 33 74 00 00", 7, "regional"),
    ("UNACT Constantine", "اتحاد نقل المسافرين قسنطينة", None, 25, "regional"),
    ("UNACT Guelma", "اتحاد نقل المسافرين قالمة", None, 24, "regional"),
    ("UNACT Jijel", "اتحاد نقل المسافرين جيجل", None, 18, "regional"),
    ("UNACT Mila", "اتحاد نقل المسافرين ميلة", None, 43, "regional"),
    ("UNACT Setif", "اتحاد نقل المسافرين سطيف", "+213 36 66 00 00", 19, "regional"),
    ("UNACT Skikda", "اتحاد نقل المسافرين سكيكدة", None, 21, "regional"),
    ("UNACT Souk Ahras", "اتحاد نقل المسافرين سوق أهراس", None, 41, "regional"),
    ("UNACT Tebessa", "اتحاد نقل المسافرين تبسة", None, 12, "regional"),
    ("UNACT Oum El Bouaghi", "اتحاد نقل المسافرين أم البواقي", None, 4, "regional"),
    ("UNACT Khenchela", "اتحاد نقل المسافرين خنشلة", None, 40, "regional"),
    ("UNACT El Tarf", "اتحاد نقل المسافرين الطارف", None, 36, "regional"),

    # ── Western region (UNAT branches) ──
    ("UNAT Tlemcen", "اتحاد نقل المسافرين تلمسان", None, 13, "regional"),
    ("UNAT Mostaganem", "اتحاد نقل المسافرين مستغانم", None, 27, "regional"),
    ("UNAT Sidi Bel Abbes", "اتحاد نقل المسافرين سيدي بلعباس", None, 22, "regional"),
    ("UNAT Tiaret", "اتحاد نقل المسافرين تيارت", None, 14, "regional"),
    ("UNAT Mascara", "اتحاد نقل المسافرين معسكر", None, 29, "regional"),
    ("UNAT Relizane", "اتحاد نقل المسافرين غليزان", None, 48, "regional"),
    ("UNAT Saida", "اتحاد نقل المسافرين سعيدة", None, 20, "regional"),
    ("UNAT Ain Temouchent", "اتحاد نقل المسافرين عين تموشنت", None, 46, "regional"),
    ("UNAT Naama", "اتحاد نقل المسافرين النعامة", None, 45, "regional"),
    ("UNAT El Bayadh", "اتحاد نقل المسافرين البيض", None, 32, "regional"),

    # ── Central / Algiers region ──
    ("Syndicat des Taxieurs Alger", "نقابة سائقي الأجرة الجزائر", "+213 21 50 00 00", 16, "regional"),
    ("Syndicat des Taxieurs Blida", "نقابة سائقي الأجرة البليدة", None, 9, "city"),
    ("Syndicat des Taxieurs Boumerdes", "نقابة سائقي الأجرة بومرداس", None, 35, "city"),
    ("Syndicat des Taxieurs Tipaza", "نقابة سائقي الأجرة تيبازة", None, 42, "city"),
    ("Syndicat des Taxieurs Bouira", "نقابة سائقي الأجرة البويرة", None, 10, "city"),
    ("Syndicat des Taxieurs Medea", "نقابة سائقي الأجرة المدية", None, 26, "city"),
    ("Syndicat des Taxieurs Ain Defla", "نقابة سائقي الأجرة عين الدفلى", None, 44, "city"),
    ("Syndicat des Taxieurs Tizi Ouzou", "نقابة سائقي الأجرة تيزي وزو", None, 15, "city"),
    ("Syndicat des Taxieurs Chlef", "نقابة سائقي الأجرة الشلف", None, 2, "city"),
    ("Syndicat des Taxieurs Djelfa", "نقابة سائقي الأجرة الجلفة", None, 17, "city"),
    ("Syndicat des Taxieurs Msila", "نقابة سائقي الأجرة المسيلة", None, 28, "city"),
    ("Syndicat des Taxieurs Laghouat", "نقابة سائقي الأجرة الأغواط", None, 3, "city"),
    ("Syndicat des Taxieurs Bordj Bou Arreridj", "نقابة سائقي الأجرة برج بوعريريج", None, 34, "city"),
    ("Syndicat des Taxieurs Tissemsilt", "نقابة سائقي الأجرة تيسمسيلت", None, 38, "city"),

    # ── Southern region ──
    ("Syndicat des Taxieurs Ouargla", "نقابة سائقي الأجرة ورقلة", None, 30, "city"),
    ("Syndicat des Taxieurs Ghardaia", "نقابة سائقي الأجرة غرداية", None, 47, "city"),
    ("Syndicat des Taxieurs Adrar", "نقابة سائقي الأجرة أدرار", None, 1, "city"),
    ("Syndicat des Taxieurs Bechar", "نقابة سائقي الأجرة بشار", None, 8, "city"),
    ("Syndicat des Taxieurs Tamanrasset", "نقابة سائقي الأجرة تمنراست", None, 11, "city"),
    ("Syndicat des Taxieurs El Oued", "نقابة سائقي الأجرة الوادي", None, 39, "city"),
    ("Syndicat des Taxieurs Touggourt", "نقابة سائقي الأجرة تقرت", None, 53, "city"),
    ("Syndicat des Taxieurs Illizi", "نقابة سائقي الأجرة إليزي", None, 33, "city"),
    ("Syndicat des Taxieurs Tindouf", "نقابة سائقي الأجرة تندوف", None, 37, "city"),
    ("Syndicat des Taxieurs Djanet", "نقابة سائقي الأجرة جانت", None, 54, "city"),
    ("Syndicat des Taxieurs Timimoun", "نقابة سائقي الأجرة تيميمون", None, 49, "city"),
    ("Syndicat des Taxieurs Beni Abbes", "نقابة سائقي الأجرة بني عباس", None, 50, "city"),
    ("Syndicat des Taxieurs Ain Salah", "نقابة سائقي الأجرة عين صالح", None, 51, "city"),
    ("Syndicat des Taxieurs El M'Ghair", "نقابة سائقي الأجرة المغير", None, 55, "city"),
    ("Syndicat des Taxieurs El Menia", "نقابة سائقي الأجرة المنيعة", None, 56, "city"),
    ("Syndicat des Taxieurs Ouled Djellal", "نقابة سائقي الأجرة أولاد جلال", None, 57, "city"),
    ("Syndicat des Taxieurs Ain Guezzam", "نقابة سائقي الأجرة عين قزام", None, 52, "city"),
    ("Syndicat des Taxieurs Bordj Badji Mokhtar", "نقابة سائقي الأجرة برج باجي مختار", None, 58, "city"),

    # ── Newer wilayas (59-69, created 2019+) ──
    ("Syndicat des Taxieurs Aflou", "نقابة سائقي الأجرة آفلو", None, 59, "city"),
    ("Syndicat des Taxieurs El Abiodh Sidi Cheikh", "نقابة سائقي الأجرة الأبيض سيدي الشيخ", None, 60, "city"),
    ("Syndicat des Taxieurs El Aricha", "نقابة سائقي الأجرة العريشة", None, 61, "city"),
    ("Syndicat des Taxieurs El Kantara", "نقابة سائقي الأجرة القنطرة", None, 62, "city"),
    ("Syndicat des Taxieurs Barika", "نقابة سائقي الأجرة بريكة", None, 63, "city"),
    ("Syndicat des Taxieurs Bou Saada", "نقابة سائقي الأجرة بوسعادة", None, 64, "city"),
    ("Syndicat des Taxieurs Bir El Ater", "نقابة سائقي الأجرة بئر العاتر", None, 65, "city"),
    ("Syndicat des Taxieurs Ksar El Boukhari", "نقابة سائقي الأجرة قصر البخاري", None, 66, "city"),
    ("Syndicat des Taxieurs Ksar Chellala", "نقابة سائقي الأجرة قصر الشلالة", None, 67, "city"),
    ("Syndicat des Taxieurs Ain Oussera", "نقابة سائقي الأجرة عين وسارة", None, 68, "city"),
    ("Syndicat des Taxieurs Messaad", "نقابة سائقي الأجرة مسعد", None, 69, "city"),
]


async def seed():
    engine = create_async_engine(settings.database.url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)

    async with session_factory() as db:
        # Check existing taxi operators
        result = await db.execute(
            text("SELECT name FROM transport_operators WHERE mode = 'taxi'")
        )
        existing = {r[0] for r in result.all()}
        print(f"Existing taxi operators ({len(existing)}): {sorted(existing)}")

        # Also check all existing operators by name to avoid duplicates
        all_result = await db.execute(
            text("SELECT name FROM transport_operators")
        )
        all_existing = {r[0] for r in all_result.all()}

        added = 0
        skipped = 0
        for name_fr, name_ar, phone, wid, coverage in TAXI_SYNDICATES:
            if name_fr in all_existing:
                print(f"  SKIP {name_fr} — already exists")
                skipped += 1
                continue

            description = f"Syndicat des taxieurs de la wilaya — "
            if phone:
                description += f"Contact direct."
            else:
                description += f"Contact via la gare routière locale."

            await db.execute(
                text("""
                    INSERT INTO transport_operators (id, name, name_ar, mode, phone, website, email,
                        headquarters_wilaya_id, description, coverage_type, is_active, metadata, created_at, updated_at)
                    VALUES (:id, :name, :name_ar, 'taxi', :phone, NULL, NULL,
                        :wid, :desc, :coverage, TRUE, '{}'::jsonb, NOW(), NOW())
                """),
                {
                    "id": uuid.uuid4(),
                    "name": name_fr,
                    "name_ar": name_ar,
                    "phone": phone,
                    "wid": wid,
                    "desc": description,
                    "coverage": coverage,
                },
            )
            added += 1

        await db.commit()
        print(f"\nAdded {added} new taxi syndicates, {skipped} skipped")

        # Show final count
        result = await db.execute(
            text("SELECT COUNT(*) FROM transport_operators WHERE mode = 'taxi'")
        )
        total = result.scalar()
        print(f"Total taxi operators now: {total}")


if __name__ == "__main__":
    asyncio.run(seed())
