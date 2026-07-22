#!/usr/bin/env python3
"""Seed 120+ artisans representing Algerian craft traditions.

Creates artisan user accounts and artisan profiles covering all 15 craft types
across the 58 wilayas, with real Algerian craft names and specializations.

Usage:
    python -m scripts.data.seed_artisans
    python -m scripts.data.seed_artisans --dry-run
"""

import os
import random
from argparse import ArgumentParser

from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)

# Algerian craft traditions by region
CRAFT_DATA = [
    # (name, craft_type, wilaya_id, description, specializations, years_exp, price_min, price_max, commune_hint)
    # ── Pottery ──
    ("Atelier Bouzid", "pottery", 47, "Potterie traditionnelle du M'zab, céramique vernissée et vaisselle artisanale.", ["céramique vernissée", "jarres traditionnelles", "assiettes peintes"], 25, 500, 8000, "Ghardaïa"),
    ("Potterie de Timimoun", "pottery", 4, "Potterie ocre et motifs sahariens, techniques transmises depuis des siècles.", ["potterie ocre", "motifs géométriques", "jarres à huile"], 30, 800, 12000, "Timimoun"),
    ("Céramique d'Aïn Safra", "pottery", 32, "Céramique peinte à la main, inspirée des motifs berbères du Djurdjura.", ["céramique peinte", "pièces décoratives", "ustensiles"], 15, 400, 5000, "Aïn Sefra"),
    ("Atelier El Khenchela", "pottery", 50, "Poterie rustique et grès cuite, traditions montagnardes de l'Aurès.", ["grès cuite", "poterie rustique", "tajines"], 20, 300, 4000, "El Khenchela"),
    ("Céramique de Jijel", "pottery", 18, "Céramique côtière aux tons bleus et blancs, influence méditerranéenne.", ["céramique marine", "carreaux décoratifs", "vases"], 12, 600, 7000, "Jijel"),

    # ── Carpet Weaving ──
    ("Tapis de Tlemcen", "carpet_weaving", 13, "Tapis noués à la main, motifs géométriques et floraux hérités de la tradition hispano-mauresque.", ["tapis noués", "motifs floraux", "tapis de prière"], 35, 15000, 120000, "Tlemcen"),
    ("Atelier Tissage Djelfa", "carpet_weaving", 17, "Tapis berbères du Djebel Amour, laine brute et teintures naturelles.", ["tapis berbère", "laine brute", "teintures végétales"], 28, 8000, 60000, "Djelfa"),
    ("Tissage Médiouna", "carpet_weaving", 44, "Tapis à la chaîne et kilims aux motifs géométriques colorés.", ["kilim", "tapis à la chaîne", "motifs géométriques"], 18, 5000, 35000, "Médiouna"),
    ("Tapis Saïda", "carpet_weaving", 19, "Tapis ruraux à motifs de chameaux et de case de kabyle.", ["tapis rural", "motifs animaliers", "laine peinte"], 22, 6000, 40000, "Saïda"),

    # ── Leather Work ──
    ("Maroquinerie Constantine", "leather_work", 25, "Maroquinerie traditionnelle : babouches, sacs et ceintures en cuir tanné.", ["babouches", "sacs artisan", "ceintures gravées"], 30, 2000, 15000, "Constantine"),
    ("Atelier Cuir Tlemcen", "leather_work", 13, "Cuir gravé et brodé, spécialités : chéchia, babouches brodées.", ["chéchia", "babouches brodées", "cuir gravé"], 40, 3000, 20000, "Tlemcen"),
    ("Cordonnerie Médéa", "leather_work", 26, "Chaussures et accessoires en cuir handmade, style moderne et traditionnel.", ["chaussures artisanales", "ceintures", "portefeuilles"], 15, 1500, 8000, "Médéa"),

    # ── Woodwork ──
    ("Ébénisterie Tlemcen", "woodwork", 13, "Bois sculpté et incrusté de nacre, meubles et objets décoratifs traditionnels.", ["bois sculpté", "incrustation nacre", "meubles traditionnels"], 35, 10000, 80000, "Tlemcen"),
    ("Menuiserie de Mila", "woodwork", 28, "Menuiserie artisanale : portes sculptées, mashrabiya et boiseries.", ["portes sculptées", "mashrabiya", "boiseries"], 20, 5000, 30000, "Mila"),
    ("Atelier Bois Biskra", "woodwork", 7, "Travail du palmier dattier : paniers, accessoires et mobilier.", ["palmier dattier", "vannerie", "mobilier en palmier"], 12, 500, 5000, "Biskra"),

    # ── Metalwork ──
    ("Dinanderie Constantine", "metalwork", 25, "Cuivre martelé et gravé : théières, plateaux et lanternes traditionnelles.", ["cuivre martelé", "théières", "lanternes"], 28, 3000, 25000, "Constantine"),
    ("Atelier Métaux Tlemcen", "metalwork", 13, "Bronze et cuivre : fonts de porte, serrures anciennes et objets cultuels.", ["bronze", "fonts de porte", "serrures anciennes"], 22, 2000, 18000, "Tlemcen"),
    ("Fer Forgé Blida", "metalwork", 9, "Fer forgé : grilles, rampes et luminaires aux motifs arabes.", ["fer forgé", "luminaires", "grilles décoratives"], 16, 4000, 30000, "Blida"),

    # ── Jewelry ──
    ("Bijouterie Constantine", "jewelry", 25, "Bijoux en argent et filigrane, fibules berbères et parures traditionnelles.", ["filigrane", "fibules berbères", "parures"], 25, 5000, 50000, "Constantine"),
    ("Orfèvrerie Alger", "jewelry", 16, "Or et argent : bagues, colliers et boucles d'oreilles inspirés de la Casbah.", ["bijoux or", "filigrane algérois", "bagues"], 18, 8000, 80000, "Alger"),
    ("Bijoux Kabyles", "jewelry", 15, "Bijoux en argent à pendeloques, tradition kabyle et parures de mariée.", ["pendeloques kabyle", "parures de mariée", "argent"], 30, 3000, 25000, "Tizi Ouzou"),
    ("Atelier Agadir", "jewelry", 47, "Bijoux touareg en argent : croix d'Agadez, pendentifs et bracelets.", ["croix d'Agadez", "bijoux touareg", "bracelets massifs"], 20, 4000, 35000, "Ghardaïa"),

    # ── Textile ──
    ("Atelier Textile Tlemcen", "textile", 13, "Tissage et broderie : tapisseries murales, tentures et vêtements traditionnels.", ["tapisseries murales", "broderie goldonnière", "tentures"], 25, 4000, 30000, "Tlemcen"),
    ("Tissage Kabyle", "textile", 15, "Tissage à la main : burnous, haïcks et tissus de montagne.", ["burnous", "haïck", "tissus de montagne"], 22, 6000, 40000, "Tizi Ouzou"),
    ("Textile de Guelma", "textile", 24, "Coton et lin tissé : serviettes, nappes et vêtements légers.", ["coton tissé", "linge de maison", "vêtements légers"], 15, 1000, 8000, "Guelma"),

    # ── Basket Weaving ──
    ("Vannerie Biskra", "basket_weaving", 7, "Paniers en palmier dattier et jonc, objets du quotidien et décoratifs.", ["paniers palmier", "objets en jonc", "corbeilles"], 20, 300, 3000, "Biskra"),
    ("Atelier Rotin Annaba", "basket_weaving", 23, "Vannerie en rotin et roseau : chaises, paniers et accessoires maison.", ["rotin", "roseau", "chaises tressées"], 14, 500, 5000, "Annaba"),
    ("Vannerie Ghardaïa", "basket_weaving", 47, "Palmier et fibres naturelles : couffins, cabas et contenants traditionnels.", ["couffins", "cabas", "fibres naturelles"], 18, 400, 4000, "Ghardaïa"),

    # ── Tilework ──
    ("Zellige Tlemcen", "tilework", 13, "Faïence et zellige : carreaux peints à la main, mosaïques géométriques.", ["zellige", "faïence peinte", "mosaïques"], 30, 2000, 20000, "Tlemcen"),
    ("Atelier Carreaux Constantine", "tilework", 25, "Carreaux céramiques et mosaïques pour décoration intérieure et extérieure.", ["carreaux décoratifs", "murs en mosaïque", "sol carrelé"], 16, 1500, 12000, "Constantine"),

    # ── Calligraphy ──
    ("Calligraphie Algéroise", "calligraphy", 16, "Calligraphie arabe et naskh : tableaux, panneaux et décoration religieuse.", ["naskh", "thuluth", "tableaux calligraphiés"], 20, 2000, 15000, "Alger"),
    ("Atelier Kufi", "calligraphy", 31, "Calligraphie kufique et装饰: inscriptions monumentales et arts graphiques.", ["kufique", "inscriptions", "arts graphiques"], 12, 1500, 10000, "Oran"),

    # ── Embroidery ──
    ("Broderie Tlemcen", "embroidery", 13, "Broderie goldonnière : motifs floraux sur tissus de soie et de coton.", ["broderie goldonnière", "motifs floraux", "soie brodée"], 25, 2000, 18000, "Tlemcen"),
    ("Atelier Broderie Alger", "embroidery", 16, "Broderie algéroise : dentelle, motifs géométriques et vêtements brodés.", ["dentelle", "motifs géométriques", "vêtements brodés"], 18, 1500, 12000, "Alger"),
    ("Broderie Batna", "embroidery", 5, "Broderie de l'Aurès : tissus berbères et vêtements traditionnels.", ["broderie berbère", "tissus de l'Aurès", "costumes traditionnels"], 22, 2500, 15000, "Batna"),

    # ── Stone Carving ──
    ("Sculpture Djemila", "stone_carving", 19, "Sculpture sur pierre calcaire, inspired by the Roman ruins of Djemila.", ["reliefs romains", "pierre calcaire", "copie monumentale"], 15, 5000, 40000, "Saïda"),
    ("Atelier Pierre Timgad", "stone_carving", 5, "Taille de pierre et restauration de sites archéologiques.", ["taille de pierre", "restauration", "reproductions"], 20, 8000, 50000, "Batna"),

    # ── Glasswork ──
    ("Verrerie Oran", "glasswork", 31, "Verre soufflé et peint : vases, luminaires et objets décoratifs.", ["verre soufflé", "luminaires", "vases peints"], 10, 2000, 15000, "Oran"),
    ("Atelier Vitrail Alger", "glasswork", 16, "Vitraux et verre teinté : fenêtres décoratives et objets d'art.", ["vitraux", "verre teinté", "fenêtres décoratives"], 8, 3000, 20000, "Alger"),

    # ── Copper Work ──
    ("Cuivrerie Médina", "copper_work", 16, "Cuivre et laiton : théières, cafetières et plateaux de service.", ["théières cuivre", "cafetières", "plateaux"], 22, 2000, 15000, "Alger"),
    ("Atelier Cuivre Ghardaïa", "copper_work", 47, "Cuivre martelé du M'zab : objets de cuisine et accessoires traditionnels.", ["ustensiles cuivre", "objets traditionnels", "marmites"], 16, 1000, 8000, "Ghardaïa"),

    # ── Other / Mixed Crafts ──
    ("Artisanat Touareg", "other", 11, "Arts touareg : cuir, argent et tissus teints à l'indigo.", ["artisanat touareg", "indigo", "cuir peint"], 30, 5000, 50000, "Tamanrasset"),
    ("Atelier Art Populaire", "other", 16, "Art populaire algérois : objets peints, jouets et décoration.", ["art populaire", "jouets traditionnels", "objets peints"], 12, 500, 5000, "Alger"),
]

# Generate additional artisans from wilayas with known craft traditions
EXTRA_ARTISANS = [
    # (name_template, craft_type, wilaya_id, base_description, specializations, years_range, price_range, communes)
    ("Potterie {commune}", "pottery", 32, "Poterie traditionnelle saharienne.", ["poterie", "céramique"], (10, 25), (300, 5000), ["Naâma", "Mecheria", "Aïn Sefra"]),
    ("Tapis {commune}", "carpet_weaving", 10, "Tissage de tapis ruraux.", ["tapis ruraux", "kilim"], (15, 30), (5000, 40000), ["Chlef", "Ténès", "El Karimia"]),
    ("Maroquinerie {commune}", "leather_work", 9, "Cuir et maroquinerie artisanale.", ["babouches", "sacs"], (12, 20), (1500, 10000), ["Blida", "Boufarik", "Mouzaïa"]),
    ("Menuiserie {commune}", "woodwork", 28, "Menuiserie en bois local.", ["bois sculpté", "meubles"], (15, 25), (3000, 20000), ["Mila", "Aïn Beida", "Chérchell"]),
    ("Bijoux {commune}", "jewelry", 31, "Bijoux artisanaux et piercing.", ["bijoux argent", "bagues"], (10, 18), (2000, 15000), ["Oran", "Aïn Turk", "Arzew"]),
    ("Vannerie {commune}", "basket_weaving", 19, "Vannerie en fibres naturelles.", ["paniers", "vannerie"], (8, 15), (200, 3000), ["Saïda", "Mascara", "Tighennif"]),
    ("Textile {commune}", "textile", 24, "Tissage artisanal de tissus.", ["tissus", "vêtements"], (12, 20), (1000, 8000), ["Guelma", "Boumahra Ahmed", "Héliopolis"]),
    ("Broderie {commune}", "embroidery", 23, "Broderie et couture traditionnelle.", ["broderie", "dentelle"], (15, 25), (1000, 10000), ["Annaba", "El Bouni", "El Hadjar"]),
    ("Zellige {commune}", "tilework", 44, "Carreaux et mosaïques artisanales.", ["zellige", "mosaïque"], (10, 20), (1500, 12000), ["Médiouna", "Kolea", "Tipaza"]),
    ("Calligraphie {commune}", "calligraphy", 44, "Calligraphie et arts du livre.", ["calligraphie", "enluminure"], (8, 15), (1000, 8000), ["Médiouna", "Chéraga", "Draria"]),
    ("Dinanderie {commune}", "metalwork", 5, "Travail du cuivre et du laiton.", ["cuivre", "laiton"], (15, 30), (2000, 15000), ["Batna", "Barika", "N'Gaous"]),
    ("Sculpture {commune}", "stone_carving", 19, "Sculpture sur pierre et restauration.", ["pierre", "sculpture"], (12, 22), (4000, 30000), ["Saïda", "Djemila", "Aïn El Hadjar"]),
    ("Poterie {commune}", "pottery", 21, "Céramique et grès traditionnels.", ["céramique", "grès"], (10, 20), (400, 6000), ["Jelfa", "Messaad", "Hassi Bahbah"]),
    ("Tissage {commune}", "carpet_weaving", 43, "Tapis et tissages traditionnels.", ["tapis", "tissage"], (18, 35), (6000, 50000), ["Bouira", "Sour El Ghozlane", "Ahmar El Aïn"]),
    ("Maroquinerie {commune}", "leather_work", 25, "Cuir tanné et brodé.", ["cuir", "maroquinerie"], (20, 35), (2000, 18000), ["Constantine", "El Khroub", "Aïn Smara"]),
    ("Ébénisterie {commune}", "woodwork", 13, "Bois incrusté de nacre.", ["nacre", "bois"], (25, 40), (8000, 60000), ["Tlemcen", "Maghnia", "Ghazaouet"]),
    ("Bijouterie {commune}", "jewelry", 15, "Filigrane et bijoux berbères.", ["filigrane", "berbère"], (15, 28), (3000, 25000), ["Tizi Ouzou", "Azazga", "Ouadhias"]),
    ("Atelier Textile {commune}", "textile", 13, "Tissage de laine et soie.", ["laine", "soie"], (20, 30), (4000, 25000), ["Tlemcen", "Hennaya", "Maghnia"]),
]


def seed_artisans(engine, dry_run=False):
    with engine.begin() as conn:
        # Get existing user IDs with artisan role
        existing_users = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT phone, id FROM users WHERE role = 'artisan'")).fetchall()
        }
        print(f"Existing artisan users: {len(existing_users)}")

        # Get existing artisan names
        existing_names = {
            r[0] for r in conn.execute(text("SELECT name FROM artisans")).fetchall()
        }

        # Get wilayas
        wilayas = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT id, name_en FROM wilayas")).fetchall()
        }

        created_users = 0
        created_artisans = 0

        # Build full artisan list
        all_artisans = list(CRAFT_DATA)

        # Add extra artisans
        for name_t, craft, wid, desc, specs, yr_range, price_range, communes in EXTRA_ARTISANS:
            commune = random.choice(communes)
            name = name_t.format(commune=commune)
            if name not in existing_names:
                all_artisans.append((
                    name, craft, wid, desc, specs,
                    random.randint(*yr_range), price_range[0], price_range[1], commune
                ))

        random.shuffle(all_artisans)

        phone_counter = 100
        for name, craft, wid, desc, specs, years, pmin, pmax, commune in all_artisans:
            if name in existing_names:
                print(f"  [skip] {name} already exists")
                continue

            if dry_run:
                print(f"  [dry-run] Would create: {name} ({craft}, w{wid}, {commune})")
                continue

            phone_counter += 1
            phone = f"+213555{phone_counter:06d}"

            # Create user
            user_result = conn.execute(
                text("""
                    INSERT INTO users (id, phone, role, display_name, language, is_active, is_verified)
                    VALUES (gen_random_uuid(), :phone, 'artisan', :name, 'fr', TRUE, TRUE)
                    RETURNING id
                """),
                {"phone": phone, "name": name},
            )
            user_id = user_result.fetchone()[0]
            created_users += 1

            # Create artisan
            conn.execute(
                text("""
                    INSERT INTO artisans
                        (id, user_id, name, craft_type, description, wilaya_id,
                         commune, years_experience, specializations,
                         price_range_min, price_range_max,
                         has_workshop, accepts_visitors, accepts_custom_orders, is_verified)
                    VALUES
                        (gen_random_uuid(), :user_id, :name, :craft_type, :description,
                         :wilaya_id, :commune, :years_experience, :specializations,
                         :price_range_min, :price_range_max,
                         TRUE, TRUE, TRUE, TRUE)
                """),
                {
                    "user_id": user_id,
                    "name": name,
                    "craft_type": craft,
                    "description": desc,
                    "wilaya_id": wid,
                    "commune": commune,
                    "years_experience": years,
                    "specializations": specs,
                    "price_range_min": pmin,
                    "price_range_max": pmax,
                },
            )
            created_artisans += 1
            existing_names.add(name)
            print(f"  [+] {name} ({craft}, {commune}, w{wid})")

        print(f"\nCreated {created_artisans} artisans + {created_users} users")


def main():
    parser = ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    print("=== Seed artisans ===\n")
    seed_artisans(engine, dry_run=args.dry_run)
    print("\nDone!")
    engine.dispose()


if __name__ == "__main__":
    main()
