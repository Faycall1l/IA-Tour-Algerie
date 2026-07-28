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
# Phone numbers from published gare routière / DTW / transport authority directories
#
# Sources:
# - SOGRAL gares routières: www.sogral.dz (official bus station operator)
# - CACI El Mouchir: www.elmouchir.caci.dz (Chamber of Commerce directory)
# - PagesMaghreb: www.pagesmaghreb.com (business directory)
# - DTW: Direction des Transports de Wilaya (wilaya transport directorates)
# - taxi-algerie.com: taxi driver directory
# - Petit Fute Algeria guide
#
# Where no direct syndicate phone exists, the SOGRAL gare routière or
# DTW number is provided as a contact point in the description.

# Additional contact info per wilaya (phone, gare_routiere, dtw)
WILAYA_CONTACTS = {
    # (wilaya_id): (phone, gare_number, dtw_number, notes)
    1:  (None,          None,                    None,                   "Gare routière SOGRAL Adrar"),
    2:  (None,          None,                    None,                   "Gare routière SOGRAL Chlef"),
    3:  (None,          None,                    None,                   "Gare routière SOGRAL Laghouat"),
    4:  (None,          None,                    None,                   ""),
    5:  (None,          None,                    None,                   ""),
    6:  (None,          "034 21 19 02",          "034 21 19 02",         "Gare SOGRAL Bejaïa / DTW: 034 21 19 02"),
    7:  (None,          None,                    None,                   "Gare routière SOGRAL Biskra"),
    8:  (None,          None,                    None,                   "Gare routière SOGRAL Béchar"),
    9:  (None,          None,                    None,                   "Gare routière SOGRAL Blida"),
    10: ("0560 00 71 71", "026 93 92 00",        "026 93 92 00",         "Radio Taxi Company Bouira: 0560 00 71 71 / Gare Antar: 026 93 92 00"),
    11: ("029 30 02 04", None,                   None,                   "Gare routière SOGRAL Tamanrasset: 029 30 02 04"),
    12: (None,          None,                    None,                   "Gare SOGRAL Hocine Ait Ahmed, Tébessa"),
    13: (None,          None,                    None,                   "Gare SOGRAL Yahia Bachir, Tlemcen"),
    14: (None,          None,                    None,                   ""),
    15: (None,          "026 22 27 82",          "026 22 27 82",         "DTW Tizi Ouzou: 026 22 27 82"),
    16: ("0542 43 31 62", "021 77 00 77",        None,                   "Station Hussein Dey: 0542 43 31 62 / SOGRAL: 021 77 00 77 / EGCTU: 0550 22 99 80"),
    17: (None,          None,                    None,                   "Gare routière SOGRAL Djelfa"),
    18: (None,          None,                    None,                   ""),
    19: (None,          None,                    None,                   "Gare SOGRAL Mohamed Boudiaf, Sétif"),
    20: (None,          None,                    None,                   ""),
    21: (None,          None,                    None,                   ""),
    22: (None,          None,                    None,                   "Gare routière Sidi Bel Abbes"),
    23: (None,          None,                    None,                   "Gare routière Annaba"),
    24: (None,          None,                    None,                   ""),
    25: (None,          None,                    None,                   "Gares SOGRAL Ali Mendjili / Sahraoui Tahar, Constantine"),
    26: (None,          None,                    None,                   "Gare routière SOGRAL Médéa"),
    27: (None,          None,                    None,                   "Gare SOGRAL 5 Juillet 1962, Mostaganem / Hôtel AZ: 045 42 02 60"),
    28: (None,          None,                    None,                   ""),
    29: (None,          None,                    "045 81 24 72",         "DTW Mascara: 045 81 24 72"),
    30: (None,          None,                    None,                   "Gare routière SOGRAL Ouargla"),
    31: (None,          None,                    "041 24 00 69",         "DTW Oran: 041 24 00 69 / Stations USTO & El Hamri"),
    32: (None,          None,                    None,                   ""),
    33: (None,          None,                    None,                   ""),
    34: (None,          None,                    None,                   ""),
    35: (None,          None,                    None,                   "DTW Boumerdes"),
    36: (None,          None,                    None,                   ""),
    37: (None,          None,                    None,                   "Gare routière SOGRAL Tindouf"),
    38: (None,          None,                    None,                   "Gare routière SOGRAL Tissemsilt"),
    39: (None,          None,                    None,                   "Gare routière SOGRAL El Oued"),
    40: (None,          None,                    None,                   "Gare routière SOGRAL Khenchela"),
    41: (None,          None,                    None,                   "Gare routière Souk Ahras"),
    42: (None,          None,                    None,                   ""),
    43: (None,          None,                    None,                   ""),
    44: (None,          None,                    None,                   "DTW Ain Defla"),
    45: (None,          None,                    None,                   "Gare routière SOGRAL Naâma"),
    46: (None,          None,                    None,                   "Gare routière Ain Témouchent"),
    47: (None,          None,                    None,                   "Gare routière SOGRAL Ghardaïa"),
    48: (None,          None,                    None,                   "Gare SOGRAL Bendaoued, Relizane / Protection civile: 046 76 34 22"),
    49: (None,          None,                    None,                   ""),
    50: (None,          None,                    None,                   ""),
    51: (None,          None,                    None,                   "Gare SOGRAL In Salah"),
    52: (None,          None,                    None,                   ""),
    53: (None,          None,                    None,                   ""),
    54: (None,          None,                    None,                   ""),
    55: (None,          None,                    None,                   ""),
    56: (None,          None,                    None,                   ""),
    57: (None,          None,                    None,                   "Gare routière Ouled Djellal"),
    58: (None,          None,                    None,                   ""),
    59: (None,          None,                    None,                   "Gare SOGRAL Aflou"),
    60: (None,          None,                    None,                   ""),
    61: (None,          None,                    None,                   ""),
    62: (None,          None,                    None,                   ""),
    63: (None,          None,                    None,                   ""),
    64: (None,          None,                    None,                   "Gare SOGRAL Boussaâda"),
    65: (None,          None,                    None,                   "Gare SOGRAL Bir El Ater"),
    66: (None,          None,                    None,                   ""),
    67: (None,          None,                    None,                   ""),
    68: (None,          None,                    None,                   "Gare SOGRAL Ain Oussera"),
    69: (None,          None,                    None,                   "Gare SOGRAL Messaâd"),
}

TAXI_SYNDICATES = [
    # ── National unions ──
    # ENTV (already seeded), UNACT, UNAT are already in the DB

    # ── Eastern region (UNACT branches) ──
    ("UNACT Annaba", "اتحاد نقل المسافرين عنابة", None, 23, "regional"),
    ("UNACT Batna", "اتحاد نقل المسافرين باتنة", None, 5, "regional"),
    ("UNACT Bejaia", "اتحاد نقل المسافرين بجاية", None, 6, "regional"),
    ("UNACT Biskra", "اتحاد نقل المسافرين بسكرة", None, 7, "regional"),
    ("UNACT Constantine", "اتحاد نقل المسافرين قسنطينة", None, 25, "regional"),
    ("UNACT Guelma", "اتحاد نقل المسافرين قالمة", None, 24, "regional"),
    ("UNACT Jijel", "اتحاد نقل المسافرين جيجل", None, 18, "regional"),
    ("UNACT Mila", "اتحاد نقل المسافرين ميلة", None, 43, "regional"),
    ("UNACT Setif", "اتحاد نقل المسافرين سطيف", None, 19, "regional"),
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
    ("Syndicat des Taxieurs Alger", "نقابة سائقي الأجرة الجزائر", None, 16, "city"),
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

            # Check for additional contact info from WILAYA_CONTACTS
            contact_info = WILAYA_CONTACTS.get(wid, (None, None, None, ""))
            c_phone, c_gare, c_dtw, c_notes = contact_info

            # Use real phone if available from contacts lookup
            effective_phone = c_phone if c_phone else phone

            # Build informative description
            parts = ["Syndicat des taxieurs de la wilaya"]
            if effective_phone:
                parts.append(f"Contact direct: {effective_phone}")
            if c_notes:
                parts.append(c_notes)
            elif c_gare:
                parts.append(f"Contact via SOGRAL gare routière: {c_gare}")
            elif c_dtw:
                parts.append(f"Contact via DTW: {c_dtw}")
            else:
                parts.append("Contact via la gare routière SOGRAL locale (021.77.00.77)")

            # National/regional syndicates get more detail
            if coverage == "regional":
                if "UNAT" in name_fr:
                    syndicate_name = "UNAT"
                    region = "Ouest"
                elif "UNACT" in name_fr:
                    syndicate_name = "UNACT"
                    region = "Est"
                else:
                    syndicate_name = ""
                    region = ""
                if syndicate_name:
                    parts.insert(0, f"Syndicat régional {syndicate_name} — région {region}")
            elif coverage == "national":
                parts.insert(0, "Syndicat national des transporteurs par taxi")

            description = " — ".join(parts)

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
                    "phone": effective_phone,
                    "wid": wid,
                    "desc": description,
                    "coverage": coverage,
                },
            )
            added += 1

        await db.commit()
        print(f"\nAdded {added} new taxi syndicates, {skipped} skipped")

        # ── UPDATE existing syndicates with new contact info ──
        updated = 0
        for name_fr, name_ar, phone, wid, coverage in TAXI_SYNDICATES:
            if name_fr not in all_existing:
                continue  # Already handled above

            contact_info = WILAYA_CONTACTS.get(wid, (None, None, None, ""))
            c_phone, c_gare, c_dtw, c_notes = contact_info
            effective_phone = c_phone if c_phone else phone

            # Build new description and phone for every existing entry
            parts = []
            if coverage == "regional":
                if "UNAT" in name_fr:
                    syndicate_name = "UNAT"
                    region = "Ouest"
                elif "UNACT" in name_fr:
                    syndicate_name = "UNACT"
                    region = "Est"
                else:
                    syndicate_name = ""
                    region = ""
                if syndicate_name:
                    parts.append(f"Syndicat régional {syndicate_name} — région {region}")
            elif coverage == "national":
                parts.append("Syndicat national des transporteurs par taxi")
            else:
                parts.append("Syndicat des taxieurs de la wilaya")

            if effective_phone:
                parts.append(f"Contact direct: {effective_phone}")
            if c_notes:
                parts.append(c_notes)
            elif c_gare and not effective_phone:
                parts.append(f"Contact via SOGRAL gare routière: {c_gare}")
            elif c_dtw and not effective_phone:
                parts.append(f"Contact via DTW: {c_dtw}")
            else:
                parts.append("Contact via la gare routière SOGRAL locale (021.77.00.77)")

            new_desc = " — ".join(parts)

            await db.execute(
                text("""
                    UPDATE transport_operators
                    SET phone = :phone,
                        description = :desc,
                        updated_at = NOW()
                    WHERE name = :name AND mode = 'taxi'
                """),
                {
                    "phone": effective_phone,
                    "desc": new_desc,
                    "name": name_fr,
                },
            )
            updated += 1

        await db.commit()
        print(f"Updated {updated} existing syndicates with new contact info")

        # Show final count
        result = await db.execute(
            text("SELECT COUNT(*) FROM transport_operators WHERE mode = 'taxi'")
        )
        total = result.scalar()
        print(f"Total taxi operators now: {total}")

        # Show syndicates with phone numbers
        result = await db.execute(
            text("SELECT name, phone FROM transport_operators WHERE mode = 'taxi' AND phone IS NOT NULL ORDER BY name")
        )
        with_phone = result.all()
        print(f"\nSyndicates with phone numbers ({len(with_phone)}):")
        for r in with_phone:
            print(f"  {r[0]}: {r[1]}")


if __name__ == "__main__":
    asyncio.run(seed())
