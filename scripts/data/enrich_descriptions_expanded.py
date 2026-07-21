"""Expand short auto-generated POI descriptions using OSM tag data.

51,816 POIs have descriptions like "Boulangerie - à Adrar" (<50 chars).
This script uses OSM tags to generate richer, more informative descriptions.

Pattern: uses osm_tags (historic, natural, amenity, tourism, etc.) to build
descriptions with specific details like elevation, architecture, year built, etc.
"""

import asyncio
import logging

from sqlalchemy import func, select, update

from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
BATCH_SIZE = 500


# ── OSM value → French description templates ──

HISTORIC_TYPES = {
    "castle": "château fort historique",
    "fort": "fortification historique",
    "ruins": "ruines historiques",
    "archaeological_site": "site archéologique",
    "monument": "monument historique",
    "memorial": "mémorial",
    "tomb": "tombeau historique",
    "battlefield": "champ de bataille historique",
    "citywalls": "remparts historiques",
    "fortress": "forteresse historique",
    "palace": "palais historique",
    "tower": "tour historique",
    "castle_wall": "enceinte de château",
    "column": "colonne historique",
    "cross": "croix historique",
    "milestone": "borne milliaire",
    "mine": "mine historique",
    "mine_shaft": "puits de mine historique",
    "monastery": "monastère historique",
    "pillory": "pilori historique",
    "rune_stone": "pierre runique",
    "ship": "épave historique",
    "stone": "pierre historique",
    "wayside_cross": "croix de chemin",
    "wayside_shrine": "oratoire",
    "wreck": "épave historique",
    "yes": "site historique",
}

AMENITY_TYPES = {
    "restaurant": "restaurant",
    "cafe": "café",
    "fast_food": "restaurant rapide",
    "pub": "bar/pub",
    "bar": "bar",
    "marketplace": "marché",
    "library": "bibliothèque",
    "theatre": "théâtre",
    "cinema": "cinéma",
    "nightclub": "boîte de nuit",
    "community_centre": "centre communautaire",
    "townhall": "mairie",
    "courthouse": "palais de justice",
    "police": "commissariat",
    "fire_station": "caserne de pompiers",
    "hospital": "hôpital",
    "clinic": "clinique",
    "pharmacy": "pharmacie",
    "bank": "banque",
    "post_office": "bureau de poste",
    "school": "école",
    "university": "université",
    "college": "collège/lycée",
    "kindergarten": "jardin d'enfants",
    "place_of_worship": "lieu de culte",
    "fountain": "fontaine",
    "shelter": "abri",
    "bench": "banc",
    "waste_basket": "corbeille",
    "toilets": "toilettes",
    "shower": "douche",
    "drinking_water": "fontaine d'eau potable",
    "parking": "parking",
    "bicycle_parking": "parking à vélos",
    "bicycle_rental": "location de vélos",
    "car_rental": "location de voitures",
    "car_wash": "station de lavage",
    "fuel": "station essence",
    "charging_station": "borne de recharge",
    "taxi": "station de taxi",
}

TOURISM_TYPES = {
    "hotel": "hôtel",
    "hostel": "auberge de jeunesse",
    "guest_house": "maison d'hôtes",
    "apartment": "appartement de vacances",
    "camp_site": "camping",
    "caravan_site": "terrain pour caravanes",
    "chalet": "chalet",
    "motel": "motel",
    "museum": "musée",
    "artwork": "œuvre d'art",
    "gallery": "galerie d'art",
    "viewpoint": "point de vue panoramique",
    "attraction": "attraction touristique",
    "theme_park": "parc d'attractions",
    "zoo": "zoo",
    "aquarium": "aquarium",
    "information": "point d'information touristique",
    "alpine_hut": "refuge de montagne",
    "wilderness_hut": "cabane en pleine nature",
    "picnic_site": "aire de pique-nique",
    "camp_pitch": "emplacement de camping",
}

NATURAL_TYPES = {
    "peak": "sommet",
    "volcano": "volcan",
    "cliff": "falaise",
    "beach": "plage",
    "bay": "baie",
    "cape": "cap",
    "valley": "vallée",
    "cave_entrance": "grotte",
    "spring": "source",
    "hot_spring": "source chaude",
    "waterfall": "cascade",
    "lake": "lac",
    "river": "rivière",
    "stream": "ruisseau",
    "strait": "détroit",
    "peninsula": "péninsule",
    "reef": "récif",
    "sand": "dune de sable",
    "scree": "éboulis",
    "sinkhole": "doline",
    "rock": "rocher",
    "stone": "pierre",
    "bay": "baie",
    "isthmus": "isthme",
    "mud": "zone boueuse",
    "geyser": "geyser",
    "glacier": "glacier",
    "tree_row": "rangée d'arbres",
    "wood": "bois/forêt",
}

LEISURE_TYPES = {
    "park": "parc",
    "garden": "jardin",
    "playground": "aire de jeux",
    "sports_centre": "centre sportif",
    "stadium": "stade",
    "pitch": "terrain de sport",
    "swimming_pool": "piscine",
    "golf_course": "terrain de golf",
    "track": "piste",
    "miniature_golf": "mini-golf",
    "nature_reserve": "réserve naturelle",
    "beach_resort": "station balnéaire",
    "marina": "marina",
    "slipway": "mise à l'eau",
    "fishing": "zone de pêche",
    "bird_hide": "observatoire ornithologique",
    "dog_park": "parc pour chiens",
    "sauna": "sauna",
    "fitness_centre": "centre de fitness",
    "water_park": "parc aquatique",
    "ice_rink": "patinoire",
}

HISTORIC_CIVILIZATIONS = {
    "romain": "romaine",
    "byzantin": "byzantine",
    "ottoman": "ottomane",
    "phoenician": "phénicienne",
    "numidian": "numide",
    "berber": "berbère",
    "andalous": "arabo-andalouse",
    "islamic": "islamique",
    "colonial": "coloniale",
    "prehistoric": "préhistorique",
    "neolithic": "néolithique",
    "roman": "romaine",
    "arab": "arabe",
    "byzantine": "byzantine",
    "punique": "punique",
    "vandale": "vandale",
    "turc": "turque/ottomane",
    "français": "coloniale française",
    "espagnol": "espagnole",
}

BUILDING_TYPES = {
    "mosque": "mosquée",
    "church": "église",
    "cathedral": "cathédrale",
    "chapel": "chapelle",
    "monastery": "monastère",
    "temple": "temple",
    "shrine": "sanctuaire",
    "synagogue": "synagogue",
    "buddhist_temple": "temple bouddhiste",
    "hindu_temple": "temple hindou",
    " tower": "tour",
    "ruins": "ruines",
    "castle": "château",
    "palace": "palais",
    "museum": "musée",
    "school": "école",
    "university": "université",
    "hospital": "hôpital",
    "station": "gare",
    "terminal": "terminal",
    "supermarket": "supermarché",
    "retail": "magasin",
    "warehouse": "entrepôt",
    "silo": "silo",
    "bunker": "bunker",
    "shed": "hangar",
    "garage": "garage",
    "carport": "carport",
    "greenhouse": "serre",
    "bridge": "pont",
    "boat": "bateau",
    "roof": "toit",
    "tent": "tente",
    "cabin": "cabane",
    "hut": "cabane",
    "bungalow": "bungalow",
    "dormitory": "dortoir",
    "house": "maison",
    "semidetached_house": "maison jumelée",
    "terrace": "maison en rangée",
    "detached": "maison individuelle",
    "apartments": "immeuble d'appartements",
    "residential": "bâtiment résidentiel",
    "farm": "ferme",
    "barn": "grange",
    "stable": "écurie",
    "cowshed": "étable",
    "church": "église",
    "chapel": "chapelle",
    "cathedral": "cathédrale",
    "shrine": "sanctuaire",
    "monastery": "monastère",
    "convent": "couvent",
}

FEATURE_TAGS = {
    "ele": "altitude",
    "height": "hauteur",
    "depth": "profondeur",
    "population": "population",
    "capacity": "capacité",
    "seats": "places",
    "rooms": "chambres",
    "beds": "lits",
    "stars": "étoiles",
    "year": "année de construction",
    "start_date": "date de construction",
    "opening_year": "année d'ouverture",
    "inscription": "année d'inscription",
    "ref:mhs": "référence monument historique",
    "wikidata": "identifiant Wikidata",
    "wikipedia": "article Wikipedia",
    "building:architect": "architecte",
    "architect": "architecte",
    "building:material": "matériau",
    "material": "matériau",
    "roof:material": "matériau de toiture",
    "building:condition": "état",
    "condition": "état",
    "access": "accès",
    "fee": "tarif",
    "charge": "tarif",
}


def _get_tag(tags: dict, *keys: str) -> str | None:
    for k in keys:
        val = tags.get(k)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _build_description(poi: POI) -> str | None:
    tags = poi.osm_tags or {}
    if not tags:
        return None

    name = poi.name or ""
    cat = poi.category or "other"
    parts: list[str] = []

    # Determine place type from OSM tags (most specific first)
    place_type = None

    # Historic
    historic = _get_tag(tags, "historic", "heritage")
    if historic and cat in ("historical", "cultural"):
        type_label = HISTORIC_TYPES.get(historic, f"site historique ({historic})")
        parts.append(f"{type_label.capitalize()}")

    # Building (religious, etc.)
    building = _get_tag(tags, "building")
    if building and cat == "religious":
        type_label = BUILDING_TYPES.get(building, f"édifice religieux ({building})")
        parts.append(f"{type_label.capitalize()}")
    elif building and not historic:
        type_label = BUILDING_TYPES.get(building, f"bâtiment ({building})")
        parts.append(f"{type_label.capitalize()}")

    # Tourism
    tourism = _get_tag(tags, "tourism")
    if tourism and cat in ("museum", "cultural"):
        type_label = TOURISM_TYPES.get(tourism, f"site touristique ({tourism})")
        parts.append(f"{type_label.capitalize()}")

    # Natural
    natural = _get_tag(tags, "natural")
    if natural and cat in ("natural", "mountain", "beach"):
        type_label = NATURAL_TYPES.get(natural, f"site naturel ({natural})")
        parts.append(f"{type_label.capitalize()}")

    # Amenity
    amenity = _get_tag(tags, "amenity")
    if amenity and cat in ("restaurant", "cafe", "market", "cultural"):
        type_label = AMENITY_TYPES.get(amenity, f"établissement ({amenity})")
        parts.append(f"{type_label.capitalize()}")

    # Leisure
    leisure = _get_tag(tags, "leisure")
    if leisure and cat in ("park", "beach", "cultural"):
        type_label = LEISURE_TYPES.get(leisure, f"espace de loisirs ({leisure})")
        parts.append(f"{type_label.capitalize()}")

    # Fallback if no type detected
    if not parts:
        cat_labels = {
            "historical": "Site historique",
            "natural": "Site naturel",
            "cultural": "Site culturel",
            "religious": "Édifice religieux",
            "museum": "Musée",
            "beach": "Plage",
            "mountain": "Sommet",
            "park": "Parc",
            "market": "Marché",
            "restaurant": "Restaurant",
            "cafe": "Café",
            "other": "Point d'intérêt",
        }
        parts.append(cat_labels.get(cat, "Point d'intérêt"))

    # Location
    if _get_tag(tags, "addr:city", "addr:village", "addr:town"):
        parts.append(f"situé à {_get_tag(tags, 'addr:city', 'addr:village', 'addr:town')}")
    elif poi.wilaya_id:
        parts.append(f"dans la wilaya {poi.wilaya_id}")

    # Add name if available and not generic
    if name and name.lower() not in ("", "non nommé", "unnamed", "sans nom"):
        parts.append(f"connu sous le nom « {name} »")

    # Civilization (for historic sites)
    historic_civ = poi.historic_civilization or _get_tag(tags, "historic:civilization", "civilization")
    if historic_civ:
        civ_fr = HISTORIC_CIVILIZATIONS.get(historic_civ.lower(), historic_civ)
        parts.append(f"de l'époque {civ_fr}")

    # Specific details from tags
    details = []

    elevation = _get_tag(tags, "ele")
    if elevation:
        try:
            ele_val = float(elevation.replace(",", "."))
            details.append(f"altitude {int(ele_val)} m")
        except (ValueError, TypeError):
            pass

    height = _get_tag(tags, "height")
    if height:
        try:
            h_val = float(height.replace(",", "."))
            details.append(f"hauteur {int(h_val)} m")
        except (ValueError, TypeError):
            pass

    year = _get_tag(tags, "start_date", "year", "opening_year", "inscription")
    if year:
        # Extract year from date string
        y = year[:4] if year[:4].isdigit() else ""
        if y:
            details.append(f"construit en {y}")

    architect = _get_tag(tags, "architect", "building:architect")
    if architect:
        details.append(f"architecte : {architect}")

    material = _get_tag(tags, "material", "building:material")
    if material:
        details.append(f"en {material}")

    access = _get_tag(tags, "access")
    if access == "yes":
        details.append("accès libre")
    elif access == "private":
        details.append("accès privé")
    elif access == "customers":
        details.append("accès réservé aux clients")

    fee = _get_tag(tags, "fee", "charge")
    if fee and fee.lower() not in ("no", "non", "free", "gratuit"):
        details.append(f"tarif : {fee}")
    elif fee and fee.lower() in ("no", "non", "free", "gratuit"):
        details.append("entrée gratuite")

    if details:
        parts.append(" — " + ", ".join(details))

    # Cuisine info
    cuisine = poi.cuisine or _get_tag(tags, "cuisine")
    if cuisine and cat in ("restaurant", "cafe"):
        parts.append(f"cuisine {cuisine}")

    # Operator
    operator = poi.operator or _get_tag(tags, "operator")
    if operator:
        parts.append(f"géré par {operator}")

    # Final assembly
    description = ". ".join(parts)
    description = description.strip(". ")
    description = description[0].upper() + description[1:] if description else ""

    # Ensure reasonable length
    if len(description) < 30:
        return None

    return description


async def main():
    async with async_session() as db:
        total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0

        result = await db.execute(
            select(POI).where(
                POI.description.isnot(None),
                func.length(POI.description) < 80,
                POI.osm_tags.isnot(None),
                POI.osm_tags != {},
            )
            .order_by(POI.is_featured.desc())
        )
        pois = result.scalars().all()

    logger.info("Found %d POIs with short descriptions + OSM tags (out of %d total)", len(pois), total)

    updated = 0
    async with async_session() as db:
        for i in range(0, len(pois), BATCH_SIZE):
            batch = pois[i : i + BATCH_SIZE]
            for poi in batch:
                new_desc = _build_description(poi)
                if new_desc and len(new_desc) >= 50:
                    await db.execute(
                        update(POI).where(POI.id == poi.id).values(description=new_desc)
                    )
                    updated += 1
            await db.commit()

            if (i // BATCH_SIZE) % 10 == 0 or i + BATCH_SIZE >= len(pois):
                logger.info(
                    "Progress: %d/%d POIs processed, %d descriptions expanded",
                    min(i + BATCH_SIZE, len(pois)), len(pois), updated,
                )

    logger.info("Done! Expanded %d POI descriptions using OSM tag data", updated)

    # Show examples
    async with async_session() as db:
        examples = await db.execute(
            select(POI.name, POI.description, POI.category).where(
                func.length(POI.description) >= 80
            ).limit(5)
        )
        logger.info("Examples of expanded descriptions:")
        for name, desc, cat in examples.all():
            logger.info("  [%s] %s: %s", cat, name[:30], desc[:120])


if __name__ == "__main__":
    asyncio.run(main())
