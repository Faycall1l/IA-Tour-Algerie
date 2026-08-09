"""Update transport_operators with real phone numbers from verified sources.

NEW SOURCES discovered in this session:
- SOGRAL official website (sogral.dz) — HQ phone + gare phones
- SNTF contacts page (sntf.dz) — regional offices
- Air Algérie agency directory — 18 wilaya offices
- vitaminedz.com — 29 intercity bus phone numbers
- tlemcen.info — SNTF station phones (Tlemcen, Maghnia, Ghazaouet)
- ETUSA official contact (algdz.com)
- SETRAM contact page
- ENTMV agence directory
- Touring Algeria network
- taxi-oran.com, taxialger.com, Yassir Oran
"""

import uuid
from sqlalchemy import create_engine, text

engine = create_engine("postgresql://athar:athar_pass@localhost:5434/athar_db")

UPDATES = [
    # ── FIX placeholder phone numbers ──
    ("SOGRAL", {"phone": "+213 21 77 00 66", "description": "National intercity bus company — connects all 69 wilayas. Contact: +213 21 77 00 66/77/88/99 (Hussein Dey). 40+ gares routières across Algeria."}),
    ("ENTV", {"phone": "+213 21 77 00 66", "description": "National transport — shared taxis and intercity connections. Contact via SOGRAL HQ: +213 21 77 00 66/77/88/99."}),

    # ── FIX ETUSA phone ──
    ("ETUSA", {"phone": "+213 21 66 74 14", "description": "Algiers urban transit — 150+ bus routes. HQ: 21 Avenue Ahmed Ghermoul, Sidi M'hamed. Tel: +213 021 66 74 14."}),

    # ── FIX SNTF HQ phone to be more accurate ──
    ("SNTF", {"phone": "+213 21 71 15 10", "description": "Société Nationale des Transports Ferroviaires — national rail operator. HQ: 21-23 Boulevard Mohamed V, Alger. Tel: +213 21 71 15 10. Regional offices in Alger, Oran, Constantine, Annaba."}),

    # ── FIX SNTF intercity line phones to regional offices ──
    ("SNTF Alger–Oran", {"phone": "+213 41 39 28 81", "description": "Alger–Oran main line via Chlef and Ain Defla. Contact SNTF Region Oran: +213 41 39 28 81 / +213 41 39 17 52."}),
    ("SNTF Alger–Constantine", {"phone": "+213 31 94 99 24", "description": "Alger–Constantine via Sétif. Contact SNTF Region Constantine: +213 31 94 99 24 / +213 31 64 10 64."}),
    ("SNTF Constantine–Annaba", {"phone": "+213 38 47 38 17", "description": "Constantine–Annaba via Guelma. Contact SNTF Region Annaba: +213 38 47 38 17 / +213 38 47 38 06."}),

    # ── Fix SETRAM Constantine with verified phone ──
    ("SETRAM Constantine", {"phone": "+213 561 726 839", "email": "sav.constantine@setram-dz.com", "description": "SETRAM Constantine unit. Address: Route de l'aéroport Frères Ferrade, Zouaghi 25021. Tel: +213.561.72.68.39."}),

    # ── UNACT Oran (fix from generic to regional) ──
    ("UNAT Oran", {"description": "UNAT Oran — Union Nationale des Transporteurs Algériens, bureau régional Ouest. Coordonne les taxis et transports inter-wilayas à la Gare Routière El Bahia et à travers l'Ouest algérien. Contact: Gare Routière El Bahia, Oran."}),
    ("UNACT Constantine", {"description": "UNACT Constantine — Union Nationale des Chauffeurs de Taxis, bureau régional Est. Gère les stations de taxis dans l'Est algérien. Contact: Gare routière Constantine."}),
]

NEW_OPERATORS = [
    # ── SNTF Regional Offices ──
    {
        "name": "SNTF Region Alger",
        "name_ar": "المنطقة الحديدية الجزائر",
        "mode": "train",
        "phone": "+213 21 73 63 66",
        "headquarters_wilaya_id": 16,
        "description": "SNTF Region ferroviaire d'Alger. Adresse: 25-27 Rue Hassiba Ben Bouali, Alger. Tel: +213 21 73 63 66 / +213 21 63 38 63.",
        "coverage_type": "regional",
    },
    {
        "name": "SNTF Region Oran",
        "name_ar": "المنطقة الحديدية وهران",
        "mode": "train",
        "phone": "+213 41 39 28 81",
        "headquarters_wilaya_id": 31,
        "description": "SNTF Region ferroviaire d'Oran. Adresse: 22 Rue Benzerdjeb, Oran. Tel: +213 41 39 28 81 / +213 41 39 17 52.",
        "coverage_type": "regional",
    },
    {
        "name": "SNTF Region Constantine",
        "name_ar": "المنطقة الحديدية قسنطينة",
        "mode": "train",
        "phone": "+213 31 94 99 24",
        "headquarters_wilaya_id": 25,
        "description": "SNTF Region ferroviaire de Constantine. Adresse: 2 Rue Nasri Said, Constantine. Tel: +213 31 94 99 24 / +213 31 64 10 64.",
        "coverage_type": "regional",
    },
    {
        "name": "SNTF Region Annaba",
        "name_ar": "المنطقة الحديدية عنابة",
        "mode": "train",
        "phone": "+213 38 47 38 17",
        "headquarters_wilaya_id": 23,
        "description": "SNTF Region ferroviaire d'Annaba. Adresse: Gare Annaba Voyageurs BP 705. Tel: +213 38 47 38 17 / +213 38 47 38 06.",
        "coverage_type": "regional",
    },

    # ── SNTF Station Phones (from tlemcen.info) ──
    {
        "name": "Gare SNTF Tlemcen",
        "name_ar": "محطة سكة حديد تلمسان",
        "mode": "train",
        "phone": "043 27 68 67",
        "headquarters_wilaya_id": 13,
        "description": "Gare ferroviaire de Tlemcen. Tel: 043 27 68 67.",
        "coverage_type": "city",
    },
    {
        "name": "Gare SNTF Maghnia",
        "name_ar": "محطة سكة حديد مغنية",
        "mode": "train",
        "phone": "040 92 24 24",
        "headquarters_wilaya_id": 13,
        "description": "Gare ferroviaire de Maghnia. Tel: 040 92 24 24.",
        "coverage_type": "city",
    },
    {
        "name": "Gare SNTF Ghazaouet",
        "name_ar": "محطة سكة حديد الغزوات",
        "mode": "train",
        "phone": "040 90 09 78",
        "headquarters_wilaya_id": 13,
        "description": "Gare ferroviaire de Ghazaouet. Tel: 040 90 09 78.",
        "coverage_type": "city",
    },

    # ── SOGRAL Gares Routières with direct phones ──
    {
        "name": "SOGRAL Gare Tamanrasset",
        "name_ar": "محطة سوقرال تمنراست",
        "mode": "bus",
        "phone": "029 30 02 04",
        "headquarters_wilaya_id": 11,
        "description": "Gare routière SOGRAL de Tamanrasset. Tel: 029 30 02 04. Gare principale de Tamanrasset pour lignes vers Alger, Sud algérien.",
        "coverage_type": "city",
    },
    {
        "name": "SOGRAL Gare Souk Ahras",
        "name_ar": "محطة سوقرال سوق أهراس",
        "mode": "bus",
        "phone": "037 71 57 72",
        "headquarters_wilaya_id": 41,
        "description": "Gare routière SOGRAL Souk Ahras — Laaraibia Mubarek Ben El Boussiri. Tel: 037 71 57 72. Lignes vers Tlemcen, Oran, Alger, Annaba, Constantine, Sud.",
        "coverage_type": "city",
    },

    # ── Air Algérie Agency Phones ──
    {
        "name": "Air Algérie Alger",
        "name_ar": "الخطوط الجوية الجزائرية الجزائر",
        "mode": "flight",
        "phone": "+213 21 68 95 05",
        "headquarters_wilaya_id": 16,
        "description": "Agence Air Algérie Alger. 1 Place Maurice Audin, Alger. Tel: +213 21 68 95 05.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Oran",
        "name_ar": "الخطوط الجوية الجزائرية وهران",
        "mode": "flight",
        "phone": "+213 41 42 72 05",
        "headquarters_wilaya_id": 31,
        "description": "Agence Air Algérie Oran. Zone des Sièges ZHUH USTO Ilots 26 / 15 Rue de l'ALN (front de mer). Tel: +213 41 42 72 05/06/07.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Constantine",
        "name_ar": "الخطوط الجوية الجزائرية قسنطينة",
        "mode": "flight",
        "phone": "+213 31 93 23 13",
        "headquarters_wilaya_id": 25,
        "description": "Agence Air Algérie Constantine. 38 Rue Abane Ramdane, Constantine. Tel: +213 31 93 23 13/56.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Annaba",
        "name_ar": "الخطوط الجوية الجزائرية عنابة",
        "mode": "flight",
        "phone": "+213 38 84 49 32",
        "headquarters_wilaya_id": 23,
        "description": "Agence Air Algérie Annaba. Carrefour Sidi Brahim, Annaba. Tel: +213 38 84 49 32/35/37.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Sétif",
        "name_ar": "الخطوط الجوية الجزائرية سطيف",
        "mode": "flight",
        "phone": "+213 36 93 64 06",
        "headquarters_wilaya_id": 19,
        "description": "Agence Air Algérie Sétif. 13 Avenue 8 Mai 1945, Sétif. Tel: +213 36 93 64 06.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Tlemcen",
        "name_ar": "الخطوط الجوية الجزائرية تلمسان",
        "mode": "flight",
        "phone": "+213 43 26 45 18",
        "headquarters_wilaya_id": 13,
        "description": "Agence Air Algérie Tlemcen. Rue du Dr Damardji Tedjani, Tlemcen. Tel: +213 43 26 45 18.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Batna",
        "name_ar": "الخطوط الجوية الجزائرية باتنة",
        "mode": "flight",
        "phone": "+213 33 81 41 03",
        "headquarters_wilaya_id": 5,
        "description": "Agence Air Algérie Batna. Rue des Frères Maazouzi, Batna. Tel: +213 33 81 41 03.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Béjaïa",
        "name_ar": "الخطوط الجوية الجزائرية بجاية",
        "mode": "flight",
        "phone": "+213 34 21 13 37",
        "headquarters_wilaya_id": 6,
        "description": "Agence Air Algérie Béjaïa. Tel: +213 34 21 13 37.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Biskra",
        "name_ar": "الخطوط الجوية الجزائرية بسكرة",
        "mode": "flight",
        "phone": "+213 33 73 34 88",
        "headquarters_wilaya_id": 7,
        "description": "Agence Air Algérie Biskra. Rue Mohamed Brahimi, Biskra. Tel: +213 33 73 34 88.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Chlef",
        "name_ar": "الخطوط الجوية الجزائرية الشلف",
        "mode": "flight",
        "phone": "+213 27 77 13 64",
        "headquarters_wilaya_id": 2,
        "description": "Agence Air Algérie Chlef. 10 Boulevard des Martyrs BP 136, Chlef. Tel: +213 27 77 13 64.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Ouargla",
        "name_ar": "الخطوط الجوية الجزائرية ورقلة",
        "mode": "flight",
        "phone": "+213 29 76 11 95",
        "headquarters_wilaya_id": 30,
        "description": "Agence Air Algérie Ouargla. Rue Souk Essabt, Ouargla. Tel: +213 29 76 11 95.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Tizi Ouzou",
        "name_ar": "الخطوط الجوية الجزائرية تيزي وزو",
        "mode": "flight",
        "phone": "+213 26 20 24 61",
        "headquarters_wilaya_id": 15,
        "description": "Agence Air Algérie Tizi Ouzou. Rue Abane Ramdane, Tizi Ouzou. Tel: +213 26 20 24 61.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Mostaganem",
        "name_ar": "الخطوط الجوية الجزائرية مستغانم",
        "mode": "flight",
        "phone": "+213 45 21 22 76",
        "headquarters_wilaya_id": 27,
        "description": "Agence Air Algérie Mostaganem. Avenue Benayed Bendhiba, Mostaganem. Tel: +213 45 21 22 76.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Adrar",
        "name_ar": "الخطوط الجوية الجزائرية أدرار",
        "mode": "flight",
        "phone": "+213 49 96 93 65",
        "headquarters_wilaya_id": 1,
        "description": "Agence Air Algérie Adrar. Place des Martyrs, Adrar. Tel: +213 49 96 93 65.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Béchar",
        "name_ar": "الخطوط الجوية الجزائرية بشار",
        "mode": "flight",
        "phone": "+213 49 81 65 65",
        "headquarters_wilaya_id": 8,
        "description": "Agence Air Algérie Béchar. 1 Place de la République, Béchar. Tel: +213 49 81 65 65.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Blida",
        "name_ar": "الخطوط الجوية الجزائرية البليدة",
        "mode": "flight",
        "phone": "+213 25 39 18 56",
        "headquarters_wilaya_id": 9,
        "description": "Agence Air Algérie Blida. Avenue des Frères Bensalah, Blida. Tel: +213 25 39 18 56.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Tindouf",
        "name_ar": "الخطوط الجوية الجزائرية تندوف",
        "mode": "flight",
        "phone": "+213 49 92 23 94",
        "headquarters_wilaya_id": 37,
        "description": "Agence Air Algérie Tindouf. Bd du 1er Novembre 54, Tindouf. Tel: +213 49 92 23 94.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Touggourt",
        "name_ar": "الخطوط الجوية الجزائرية تقرت",
        "mode": "flight",
        "phone": "+213 29 68 26 68",
        "headquarters_wilaya_id": 53,
        "description": "Agence Air Algérie Touggourt. Centre Ville, Touggourt. Tel: +213 29 68 26 68.",
        "coverage_type": "city",
    },
    {
        "name": "Air Algérie Timimoun",
        "name_ar": "الخطوط الجوية الجزائرية تيميمون",
        "mode": "flight",
        "phone": "+213 49 90 45 55",
        "headquarters_wilaya_id": 49,
        "description": "Agence Air Algérie Timimoun. Place de l'Indépendance, Timimoun. Tel: +213 49 90 45 55.",
        "coverage_type": "city",
    },

    # ── ENTMV Ferry/Travel Agencies ──
    {
        "name": "ENTMV Sétif",
        "name_ar": "الشركة الوطنية للنقل البحري سطيف",
        "mode": "ferry",
        "phone": "036 93 75 70",
        "headquarters_wilaya_id": 19,
        "description": "Agence ENTMV Sétif. 2 Avenue du 1er Novembre 1954, Sétif. Billetterie ferry. Tel: 036.93.75.70.",
        "coverage_type": "city",
    },
    {
        "name": "ENTMV Constantine",
        "name_ar": "الشركة الوطنية للنقل البحري قسنطينة",
        "mode": "ferry",
        "phone": "031 87 25 79",
        "headquarters_wilaya_id": 25,
        "description": "Agence ENTMV Constantine. 16 Rue Didouche Mourad, Constantine. Tel: 031.87.25.79.",
        "coverage_type": "city",
    },
    {
        "name": "ENTMV Annaba",
        "name_ar": "الشركة الوطنية للنقل البحري عنابة",
        "mode": "ferry",
        "phone": "038 86 58 47",
        "headquarters_wilaya_id": 23,
        "description": "Agence ENTMV Annaba. 17 Cour de la Révolution, Annaba. Tel: 038.86.58.47.",
        "coverage_type": "city",
    },
    {
        "name": "ENTMV Skikda",
        "name_ar": "الشركة الوطنية للنقل البحري سكيكدة",
        "mode": "ferry",
        "phone": "038 76 34 22",
        "headquarters_wilaya_id": 21,
        "description": "Agence ENTMV Skikda. 10 Avenue Zighout Youcef, Skikda. Tel: 038.76.34.22.",
        "coverage_type": "city",
    },
    {
        "name": "ENTMV Guelma",
        "name_ar": "الشركة الوطنية للنقل البحري قالمة",
        "mode": "ferry",
        "phone": "037 26 12 27",
        "headquarters_wilaya_id": 24,
        "description": "Agence ENTMV Guelma. 5 Rue Ferdes Hocine, Guelma. Tel: 037.26.12.27.",
        "coverage_type": "city",
    },

    # ── SETRAM regional units ──
    {
        "name": "SETRAM Sétif",
        "name_ar": "سيترام سطيف",
        "mode": "tram",
        "email": "sav.setif@setram-dz.com",
        "headquarters_wilaya_id": 19,
        "description": "SETRAM Sétif unit — tramway operator for Sétif city (23 stations).",
        "coverage_type": "city",
    },

    # ── Touring Algeria (auto/travel assistance) ──
    {
        "name": "Touring Algeria Constantine",
        "name_ar": "تورينغ الجزائر قسنطينة",
        "mode": "taxi",
        "phone": "+213 31 92 67 72",
        "headquarters_wilaya_id": 25,
        "description": "Touring Algeria — agence de Constantine. 35 Avenue Aouti Mostefa. Tel: +213 31 92 67 72 / 031 92 96 34. Assistance voyage et location.",
        "coverage_type": "regional",
    },
    {
        "name": "Touring Algeria Annaba",
        "name_ar": "تورينغ الجزائر عنابة",
        "mode": "taxi",
        "phone": "+213 38 45 22 62",
        "headquarters_wilaya_id": 23,
        "description": "Touring Algeria — agence d'Annaba. 1 Bd Zirout Youcef, Annaba. Tel: +213 038 45 22 62.",
        "coverage_type": "regional",
    },

    # ── Taxi/VTC operators with real contact info ──
    {
        "name": "TaxiAlger",
        "name_ar": "تاكسي الجزائر",
        "mode": "taxi",
        "phone": "+213 772 15 87 94",
        "website": "https://taxialger.com",
        "headquarters_wilaya_id": 16,
        "description": "Service de réservation de taxi Alger et inter-wilayas. Tel: +213 772 15 87 94 (samedi-jeudi, 10h-18h).",
        "coverage_type": "city",
    },
    {
        "name": "TAXI ORAN 31",
        "name_ar": "تاكسي وهران 31",
        "mode": "taxi",
        "phone": None,
        "website": "https://taxioran.com",
        "headquarters_wilaya_id": 31,
        "description": "Service de taxi Oran 24h/24. Inter-wilayas à partir de 5000 DZD. Contact via taxioran.com ou WhatsApp.",
        "coverage_type": "city",
    },
    {
        "name": "Yassir Oran",
        "name_ar": "ياسير وهران",
        "mode": "taxi",
        "phone": "+213 550 71 45 49",
        "headquarters_wilaya_id": 31,
        "description": "Yassir Oran — VTC et taxi. Point Du Jour, Cité n°34, 1er étage, Oran 31000. Tel: +213 550 71 45 49 (WhatsApp).",
        "coverage_type": "city",
    },
]


with engine.connect() as conn:
    # ── UPDATE existing operators ──
    for name, fields in UPDATES:
        set_parts = []
        params = {"name": name}
        for col, val in fields.items():
            set_parts.append(f"{col} = :{col}")
            params[col] = val
        set_parts.append("updated_at = NOW()")
        sql = f"UPDATE transport_operators SET {', '.join(set_parts)} WHERE name = :name"
        r = conn.execute(text(sql), params)
        if r.rowcount:
            print(f"  UPDATED: {name} ({r.rowcount} rows)")
        else:
            print(f"  NOT FOUND: {name}")

    # ── INSERT new operators ──
    for op in NEW_OPERATORS:
        r = conn.execute(text("SELECT id FROM transport_operators WHERE name = :name"), {"name": op["name"]})
        if r.fetchone():
            print(f"  SKIP (exists): {op['name']}")
            continue

        op_id = uuid.uuid4()
        conn.execute(
            text("""
                INSERT INTO transport_operators (id, name, name_ar, mode, phone, website, email,
                    headquarters_wilaya_id, description, coverage_type, is_active, metadata, created_at, updated_at)
                VALUES (:id, :name, :name_ar, :mode, :phone, :website, :email,
                    :hq_wid, :description, :coverage_type, true, '{}'::jsonb, NOW(), NOW())
            """),
            {
                "id": op_id,
                "name": op["name"],
                "name_ar": op.get("name_ar"),
                "mode": op["mode"],
                "phone": op.get("phone"),
                "website": op.get("website"),
                "email": op.get("email"),
                "hq_wid": op.get("headquarters_wilaya_id"),
                "description": op.get("description"),
                "coverage_type": op.get("coverage_type", "city"),
            },
        )
        print(f"  INSERTED: {op['name']} ({op['mode']})")

    conn.commit()

# Show final counts
with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT mode, COUNT(*),
               COUNT(*) FILTER (WHERE phone IS NOT NULL) as with_phone
        FROM transport_operators GROUP BY mode ORDER BY mode
    """))
    print("\nFinal operator counts by mode:")
    for row in r:
        print(f"  {row[0]:15s} → {row[1]:3d} total, {row[2]:3d} with phone")

    r = conn.execute(text("SELECT COUNT(*) FROM transport_operators"))
    print(f"\nTotal operators: {r.scalar()}")

    r = conn.execute(text("SELECT COUNT(*) FROM transport_operators WHERE phone IS NOT NULL"))
    print(f"Operators with phone numbers: {r.scalar()}")

    print("\nAll operators with real phone numbers:")
    r = conn.execute(text("SELECT name, phone FROM transport_operators WHERE phone IS NOT NULL ORDER BY name"))
    for row in r:
        print(f"  {row[0]:35s} {row[1]}")

engine.dispose()
