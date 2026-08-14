#!/usr/bin/env python3
"""Map PagesMaghreb business categories to the DB `craft_type` enum.

Every PM record carries one or more French business categories (e.g.
"Céramique (artisanat)", "Bijouterie horlogerie"). This classifier maps them to
one of the 15 ARTISAN_CRAFTS values, with explicit per-category overrides first,
then keyword rules, then a fallback to "other". Categories that are clearly NOT
artisan work (construction, auto repair, industrial machinery, imported retail
of non-craft goods) are excluded from the corpus entirely.

No synthetic data: a firm only keeps the mapped craft when the source category
is genuinely a craft; otherwise it is dropped (logged).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PM_JSON = REPO / "app" / "data" / "pagesmaghreb_artisans.json"
OUT_JSON = REPO / "app" / "data" / "pm_artisans_mapped.json"
REPORT = REPO / "scripts" / "data" / "reports" / "pm_craft_mapping.txt"

# Explicit category → craft_type overrides (exact match wins).
EXACT = {
    "Poterie": "pottery",
    "Poterie, faïencerie (artisanat)": "pottery",
    "Céramiques d'art": "pottery",
    "Céramique (artisanat)": "pottery",
    "Céramiques (fabrication)": "pottery",
    "Céramiques (autres que sanitaire)": "pottery",
    "Porcelaines, faïences (fabrication, gros)": "pottery",
    "Faïences : vaisselle": "pottery",
    "Mosaïques et céramiques": "tilework",
    "Faïences : carrelage": "tilework",
    "Carreaux céramiques": "tilework",
    "Carrelages, dallages (vente, pose, traitement)": "tilework",
    "Tapis (détail)": "carpet_weaving",
    "Tapis (fabrication)": "carpet_weaving",
    "Moquettes, tapis (détail)": "carpet_weaving",
    "Moquettes (fabrication et gros)": "carpet_weaving",
    "Tapis, revêtements textiles (fabrication)": "carpet_weaving",
    "Tapis et tapisseries (reproduction, réparation, restauration)": "carpet_weaving",
    "Tapis d'orient et d'artisanat": "carpet_weaving",
    "Reproductions de tapis et tapisseries": "carpet_weaving",
    "Tapisserie d'art": "carpet_weaving",
    "Restauration de tapis": "carpet_weaving",
    "Commerce de détail de tapis, exercé en étal": "carpet_weaving",
    "Tissage": "textile",
    "Broderies (artisanat)": "embroidery",
    "Broderies (détail)": "embroidery",
    "Broderies, dentelles et tulles (fabrication)": "embroidery",
    "Broderies, marquages à façon": "embroidery",
    "Maroquinerie traditionnelle (détail)": "leather_work",
    "Maroquinerie (artisanat)": "leather_work",
    "Maroquinerie : articles (détail)": "leather_work",
    "Maroquinerie : articles (fabrication)": "leather_work",
    "Artisanat et maroquinerie traditionnelle (gros)": "leather_work",
    "Maroquinerie (réparation)": "leather_work",
    "Commerce de détail de la maroquinerie traditionnelle, exercé en étal": "leather_work",
    "Travail du cuir": "leather_work",
    "Sellerie maroquinerie": "leather_work",
    "Harnachement et sellerie (fabrication)": "leather_work",
    "Sellerie et harnachement (détail)": "leather_work",
    "Chaussures (fabrication)": "leather_work",
    "Cordonneries": "leather_work",
    "Vêtements de cuir et de peau (détail)": "leather_work",
    "Ebénisterie": "woodwork",
    "Ebénisterie d'art, restauration de meubles": "woodwork",
    "Menuiserie (entreprises)": "woodwork",
    "Menuiserie de bois": "woodwork",
    "Menuiserie générale": "woodwork",
    "Menuiserie du bâtiment": "woodwork",
    "Bois d'ébénisterie": "woodwork",
    "Bois (transformation)": "woodwork",
    "Bois (sculpture)": "woodwork",
    "Restauration de meubles": "woodwork",
    "Meubles (réparation, restauration)": "woodwork",
    "Meubles d'art et anciens": "woodwork",
    "Meubles de style et contemporains (commerce)": "woodwork",
    "Meubles en rotin (fabrication, commerce)": "basket_weaving",
    "Salons": "woodwork",
    "Salons et sièges (détail)": "woodwork",
    "Lits escamotables": "woodwork",
    "Ameublement en bois à usage domestique ou hôtelier (fabrication industrielle)": "woodwork",
    "Vannerie (détail)": "basket_weaving",
    "Vannerie (fabrication)": "basket_weaving",
    "Sparterie et vannerie": "basket_weaving",
    "Vannerie et sparterie (gros)": "basket_weaving",
    "Rotins": "basket_weaving",
    "Ferronnerie d'art": "metalwork",
    "Ferronnerie et menuiserie métallique (artisanat)": "metalwork",
    "Ferronnerie et menuiserie métallique": "metalwork",
    "Ferronnerie (artisanat)": "metalwork",
    "Fer forgé": "metalwork",
    "Serrurerie, métallerie": "metalwork",
    "Cuivre": "copper_work",
    "Cuivrerie et dinanderie": "copper_work",
    "Dinanderie (détail)": "copper_work",
    "Dinanderie et cuivrerie": "copper_work",
    "Verrerie d'art, verrerie soufflée (fabrication, gros)": "glasswork",
    "Verrerie d'art": "glasswork",
    "Verrerie": "glasswork",
    "Vitraux": "glasswork",
    "Souffleurs de verre": "glasswork",
    "Impression sur verre": "glasswork",
    "Gravure, peinture et décoration sur verre et glace": "glasswork",
    "Bijouterie (entreprise artisanale)": "jewelry",
    "Bijouterie horlogerie": "jewelry",
    "Bijouterie traditionnelle et horlogerie (détail)": "jewelry",
    "Bijouterie joaillerie (fabrication, transformation)": "jewelry",
    "Bijouterie fantaisie (détail)": "jewelry",
    "Bijouterie fantaisie (fabrication, gros)": "jewelry",
    "Bijouterie, joaillerie : matériel et fournitures": "jewelry",
    "Bijoutiers (fabrication, gros)": "jewelry",
    "Joaillerie (création, fabrication)": "jewelry",
    "Bijoux anciens et d'occasion (achat et vente)": "jewelry",
    "Bijoux (production industrielle)": "jewelry",
    "Experts en bijoux et en joaillerie": "jewelry",
    "Graveurs en bijoux et médailles": "jewelry",
    "Montres, horloges": "jewelry",
    "Horlogerie (détail)": "jewelry",
    "Horlogerie et bijouterie (gros, détail)": "jewelry",
    "Corail (Fabrication)": "jewelry",
    "Corail (transformation)": "jewelry",
    "Diamants, pierres précieuses et pierres gemmes (travail des)": "jewelry",
    "Coffrets et écrins": "jewelry",
    "Couture (haute couture, création)": "textile",
    "Couture et confection (façonniers)": "textile",
    "Couture, retouches": "textile",
    "Haute couture": "textile",
    "Robes et parures de mariées (confection, détail)": "textile",
    "Vêtements pour femmes (détail)": "textile",
    "Vêtements (confection)": "textile",
    "Vêtements sur mesure": "textile",
    "Vêtements pour femmes (fabrication)": "textile",
    "Vêtements et lingerie (confection)": "textile",
    "Prêt-à-porter": "textile",
    "Boutiques de prêt-à-porter": "textile",
    "Linge de maison (détail)": "textile",
    "Rideaux, voilages et tissus d'ameublement (détail)": "textile",
    "Tissus (commerce)": "textile",
    "Tringles à rideaux": "textile",
    "Voilages": "textile",
    "Nappes": "textile",
    "Couettes": "textile",
    "Couvertures, couettes (importation, exportation)": "textile",
    "Bonneterie (artisanat)": "textile",
    "Toiles industrielles et ouvrages en tissus (fabrication)": "textile",
    "Bâches et toiles (fabrication)": "textile",
    "Stores : fournitures pour": "textile",
    "Fils à coudre": "textile",
    "Textiles : fournitures et accessoires (importation)": "textile",
    "Habillement et textiles": "textile",
    "Habillement": "textile",
    "Finissage de textiles (blanchiment, teinture, impression et apprêts)": "textile",
    "Marbre (ponçage)": "stone_carving",
    "Marbres, granits et pierres naturelles": "stone_carving",
    "Peinture artistique : fournitures": "other",
    "Tableaux et œuvres d'art (détail)": "other",
    "Galeries d'art": "other",
    "Artistes peintres": "other",
    "Artistes": "other",
    "Œuvres d’art (fabrication)": "other",
    "Œuvres d’art (Vente)": "other",
    "Restauration de tableaux": "other",
    "Sérigraphie": "other",
    "Arts graphiques, arts plastiques : matériel et fournitures (détail)": "other",
    "Instruments de musique et accessoires": "other",
    "Décoration artistique": "other",
    "Décoration (fabrication)": "other",
    "Décorateurs": "other",
    "Designers": "other",
    "Architectes d'intérieur": "other",
    "Lustrerie et décoration d'intérieur (détail)": "other",
    "Décoration d'intérieur et lustrerie (importation, exportation)": "other",
    "Lustres (importation, exportation)": "other",
    "Décoration lumineuse": "other",
    "Lampes, lampadaires": "other",
    "Dessin (ateliers)": "other",
    "Mariage": "other",
    "Articles de fête": "other",
    "Cadeaux (détail)": "other",
    "Artisanat d'art": "other",
    "Artisanat (détail)": "other",
    "Artisanat et travaux manuels : fournitures (détail)": "other",
    "Artisanat (importation, exportation)": "other",
    "Equipement domestique et artisanat": "other",
    "Production artisanale": "other",
    "A découvrir > artisanat": "other",
    "Chambre de l'artisanat et des métiers": "other",
    "Artisanat (administration)": "other",
    "Agence nationale de l'artisanat traditionnel": "other",
    "Promotion des produits de l'artisanat": "other",
}

# Substring rules applied only when EXACT doesn't match (priority order).
KEYWORD = [
    ("pottery", ["poterie", "céramique", "ceramique", "faïence", "porcelaine", "mosaïques et"]),
    ("tilework", ["carreaux", "carrelage", "carrelages", "faïences"]),
    ("carpet_weaving", ["tapis", "moquette", "tapisserie"]),
    ("embroidery", ["broderie", "broder", "dentelle", "tulle"]),
    ("leather_work", ["maroquinerie", "cuir", "sellerie", "harnachement", "cordonnerie", "chaussures"]),
    ("woodwork", ["ébénisterie", "ebénisterie", "menuisier", "bois", "meuble", "meubles", "ameublement", "salons"]),
    ("basket_weaving", ["vannerie", "sparterie", "rotin", "rotins"]),
    ("metalwork", ["ferronnerie", "fer forgé", "fer forge", "métallique", "serrurerie", "métallerie", "métaux", "chaudronnerie", "mobilier métallique", "ferronnerie"]),
    ("copper_work", ["cuivre", "cuivrerie", "dinanderie"]),
    ("glasswork", ["verrerie", "verre", "vitrail", "vitraux", "cristallerie", "souffleur"]),
    ("jewelry", ["bijouterie", "bijoux", "joaillerie", "joaillerie", "horlogerie", "horloge", "montres", "corail", "diamants", "écrins", "gravure en bijoux"]),
    ("stone_carving", ["marbre", "granit", "pierre", "sculpture sur"]),
    ("textile", ["couture", "vêtement", "lingerie", "habillement", "bonneterie", "tissus", "tissu", "rideau", "voilage", "tringle", "confection", "prêt-à-porter", "pret-a-porter", "nappe", "couette", "toiles", "stores", "fils à coudre", "textile", "finissage"]),
    ("other", ["artisanat", "décoration", "decoration", "lustrerie", "peinture", "galerie", "tableau", "œuvres", "oeuvres", "sculpture", "maroquinerie"]),
]

# Categories that are NOT artisan work (construction, auto, machinery, wholesale
# of non-craft goods). A firm with ONLY these categories is excluded.
EXCLUDE_KEYWORDS = [
    "bâtiment", "batiment", "maçonnerie", "maconnerie", "étanchéité", "etancheite",
    "plâtrerie", "platre", "plomberie", "électricité", "electricite", "espace vert",
    "façade", "facade", "terrasse", "balcon", "sols industriels", "charpente",
    "construction métallique", "portes blindées", "portes automatiques", "portails",
    "porte coupe-feu", "mobilier urbain", "monte-charge", "élévateur", "elevateur",
    "maisons préfabriquées", "revêtements des murs", "sanitaires", "appareils sanitaires",
    "salles de bain", "automatisme", "contrôle d'accès", "contrôle technique",
    "agence de publicité", "automobile", "automobiles", "garage", "carrosserie",
    "location d'automobiles", "location d'engins", "huiles de vidange", "manutention",
    "moteur", "compresseur", "groupe électrogène", "machines pour l'industrie textile",
    "machines et matériel électrique", "équipement industriel", "equipement industriel",
    "outillage", "abrasifs", "fonderie", "fonderies", "métaux non ferreux",
    "ressorts", "import-export de", "import-export de tous", "commerce de gros de matériel",
    "commerce de gros de matériaux", "commerce de gros de la maroquinerie", "commerces de gros",
    "électroménager", "electromenager", "informatique", "machines de bureau",
    "confiseries", "chocolateries", "plantes", "deltaplane", "maçonnerie",
    "carrelages, dallages (vente, pose", "climatisation", "chauffage",
    "miroiterie", "miroir", "photographe", "coiffure", "salon de beauté",
    "contrôle : appareils", "vérins", "treuils", "palans", "pompes",
    "fabrication industrielle", "production industrielle de", "commerce de détail de matériel",
    "commerce de gros", "importation, exportation", "matériel et équipements industriels",
    "contrôle : appareils", "fibres synthétiques", "vêtements de pluie",
    "prêt-à-porter (importation", "confection industrielle", "textile (importation",
]

# Categories that look like artisan retail/supply but are NOT a workshop — we
# keep them only if the firm ALSO has a real craft category.
SUPPLY_ONLY = {
    "Artisanat et travaux manuels : fournitures (détail)",
    "Décoration : matériel et fournitures",
    "Décoration : matériel et fournitures (importation, exportation)",
    "Peinture artistique : fournitures",
    "Couture : fournitures pour",
    "Céramiques : matériel et fournitures",
    "Bijouterie : matériel et fournitures (fabrication)",
    "Bijouterie, joaillerie : matériel et fournitures",
    "Céramiques (gros)",
}


def classify_categories(categories: list[str]) -> str | None:
    """Return the best craft_type for a firm, or None if it should be excluded."""
    if not categories:
        return None

    cats = [c.strip() for c in categories if c and c.strip()]
    if not cats:
        return None

    # A firm that is ONLY a supply shop (no craft) is not a workshop. This must
    # be checked before EXACT, since some SUPPLY_ONLY categories also carry an
    # EXACT "other" override.
    if all(c in SUPPLY_ONLY for c in cats):
        return None

    # Explicit overrides first.
    for c in cats:
        if c in EXACT:
            return EXACT[c]

    # Excluded categories: if every category is a non-craft trade, drop firm.
    if all(any(k in c.lower() for k in EXCLUDE_KEYWORDS) for c in cats):
        return None

    # Keyword rules in priority order.
    for craft, kws in KEYWORD:
        for kw in kws:
            if any(kw in c.lower() for c in cats):
                return craft

    # Mixed artisan + supply -> other.
    if any("artisanat" in c.lower() for c in cats) or any(
        "artisan" in c.lower() for c in cats
    ):
        return "other"

    return None


def main() -> None:
    with open(PM_JSON) as fh:
        data = json.load(fh)
    mapped = []
    dropped = []
    unmapped_cats: set[str] = set()

    for rec in data:
        cats = rec.get("categories", [])
        craft = classify_categories(cats)
        if craft is None:
            dropped.append(rec)
            for c in cats:
                kw_hits = [k for _, kws in KEYWORD for k in kws]
                if c not in EXACT and not any(
                    k in c.lower() for k in [*EXCLUDE_KEYWORDS, *kw_hits]
                ):
                    unmapped_cats.add(c)
            continue
        rec["craft_type"] = craft
        rec["craft_categories"] = (
            [
                c
                for c in cats
                if c in EXACT
                or any(k in c.lower() for k in [k for _, kws in KEYWORD for k in kws])
            ]
            or cats[:2]
        )
        mapped.append(rec)

    with open(OUT_JSON, "w") as fh:
        json.dump(mapped, fh, ensure_ascii=False, indent=1)
    print(f"mapped: {len(mapped)}  dropped: {len(dropped)}")
    print(f"unmapped categories (not in any rule): {len(unmapped_cats)}")
    for c in sorted(unmapped_cats):
        print("  -", c)
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    sys.exit(main())
