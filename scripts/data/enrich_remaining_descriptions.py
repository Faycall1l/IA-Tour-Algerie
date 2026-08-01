#!/usr/bin/env python3
"""Generate descriptions for remaining ~10K POIs directly from osm_tags JSONB.

Handles unnamed POIs (non nommé, Unknown) by extracting tag values. Generates
both FR and EN descriptions. Uses smart tag value → label mapping.
"""

import os
import sys
from collections import defaultdict

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

# ── Tag value → descriptive label (FR) ──
TAG_FR = defaultdict(lambda: None, {
    # shop
    ("shop", "bakery"): "Boulangerie",
    ("shop", "confectionery"): "Confiserie",
    ("shop", "supermarket"): "Supermarché",
    ("shop", "gift"): "Boutique de cadeaux",
    ("shop", "souvenir"): "Boutique de souvenirs",
    ("shop", "mall"): "Centre commercial",
    ("shop", "books"): "Librairie",
    ("shop", "clothes"): "Magasin de vêtements",
    ("shop", "electronics"): "Magasin d'électronique",
    ("shop", "florist"): "Fleuriste",
    ("shop", "butcher"): "Boucherie",
    ("shop", "greengrocer"): "Fruits et légumes",
    ("shop", "pastry"): "Pâtisserie",
    ("shop", "art"): "Galerie d'art",
    ("shop", "furniture"): "Magasin de meubles",
    ("shop", "jewelry"): "Bijouterie",
    ("shop", "wine"): "Cave à vin",
    ("shop", "car"): "Concessionnaire automobile",
    ("shop", "car_repair"): "Garage automobile",
    ("shop", "hairdresser"): "Salon de coiffure",
    ("shop", "optician"): "Opticien",
    ("shop", "chemist"): "Pharmacie",
    ("shop", "tobacco"): "Marchand de tabac",
    ("shop", "kiosk"): "Kiosque",
    ("shop", "department_store"): "Grand magasin",
    ("shop", "hardware"): "Quincaillerie",
    ("shop", "stationery"): "Papeterie",
    ("shop", "sports"): "Magasin de sport",
    ("shop", "mobile_phone"): "Téléphonie mobile",
    ("shop", "beauty"): "Institut de beauté",
    ("shop", "travel_agency"): "Agence de voyages",
    ("shop", "laundry"): "Blanchisserie",
    ("shop", "dry_cleaning"): "Nettoyage à sec",
    ("shop", "bicycle"): "Magasin de vélos",
    ("shop", "variety_store"): "Bazar",
    ("shop", "convenience"): "Épicerie",
    # amenity
    ("amenity", "cafe"): "Café",
    ("amenity", "bar"): "Bar",
    ("amenity", "restaurant"): "Restaurant",
    ("amenity", "fast_food"): "Restauration rapide",
    ("amenity", "library"): "Bibliothèque",
    ("amenity", "internet_cafe"): "Cybercafé",
    ("amenity", "public_bath"): "Hammam / Bains publics",
    ("amenity", "pharmacy"): "Pharmacie",
    ("amenity", "bank"): "Banque",
    ("amenity", "post_office"): "Bureau de poste",
    ("amenity", "place_of_worship"): "Lieu de culte",
    ("amenity", "school"): "École",
    ("amenity", "university"): "Université",
    ("amenity", "college"): "Collège",
    ("amenity", "hospital"): "Hôpital",
    ("amenity", "clinic"): "Clinique",
    ("amenity", "dentist"): "Dentiste",
    ("amenity", "police"): "Commissariat de police",
    ("amenity", "fire_station"): "Caserne de pompiers",
    ("amenity", "townhall"): "Mairie",
    ("amenity", "community_centre"): "Centre communautaire",
    ("amenity", "cinema"): "Cinéma",
    ("amenity", "theatre"): "Théâtre",
    ("amenity", "fuel"): "Station-service",
    ("amenity", "parking"): "Parking",
    ("amenity", "bus_station"): "Gare routière",
    ("amenity", "taxi"): "Station de taxi",
    ("amenity", "atm"): "Distributeur automatique",
    ("amenity", "bureau_de_change"): "Bureau de change",
    ("amenity", "nightclub"): "Boîte de nuit",
    ("amenity", "casino"): "Casino",
    ("amenity", "marketplace"): "Marché",
    # man_made
    ("man_made", "tower"): "Tour",
    ("man_made", "water_tower"): "Château d'eau",
    ("man_made", "lighthouse"): "Phare",
    ("man_made", "obelisk"): "Obélisque",
    ("man_made", "monument"): "Monument",
    ("man_made", "statue"): "Statue",
    ("man_made", "cross"): "Croix",
    ("man_made", "mast"): "Mât",
    ("man_made", "chimney"): "Cheminée",
    ("man_made", "silo"): "Silo",
    ("man_made", "storage_tank"): "Réservoir",
    ("man_made", "water_well"): "Puits",
    ("man_made", "watermill"): "Moulin à eau",
    ("man_made", "windmill"): "Moulin à vent",
    # tower:type
    ("tower:type", "communication"): "Tour de communication",
    ("tower:type", "watchtower"): "Tour de guet",
    ("tower:type", "minaret"): "Minaret",
    ("tower:type", "observation"): "Tour d'observation",
    ("tower:type", "lighting"): "Tour d'éclairage",
    ("tower:type", "defensive"): "Tour défensive",
    ("tower:type", "bell_tower"): "Clocher",
    ("tower:type", "clock"): "Tour de l'horloge",
    ("tower:type", "cooling"): "Tour de refroidissement",
    ("tower:type", "radar"): "Radar",
    ("tower:type", "lookout"): "Tour panoramique",
    # historic
    ("historic", "archaeological_site"): "Site archéologique",
    ("historic", "ruins"): "Ruines historiques",
    ("historic", "memorial"): "Mémorial",
    ("historic", "monument"): "Monument historique",
    ("historic", "castle"): "Château historique",
    ("historic", "fort"): "Fort historique",
    ("historic", "battlefield"): "Champ de bataille",
    ("historic", "tomb"): "Tombeau historique",
    ("historic", "citywalls"): "Remparts historiques",
    ("historic", "pillory"): "Pilori",
    ("historic", "milestone"): "Borne historique",
    ("historic", "manor"): "Manoir",
    ("historic", "palace"): "Palais historique",
    ("historic", "aqueduct"): "Aqueduc historique",
    ("historic", "bridge"): "Pont historique",
    ("historic", "tower"): "Tour historique",
    ("historic", "wayside_cross"): "Croix de chemin",
    ("historic", "wayside_shrine"): "Chapelle de chemin",
    ("historic", "mine"): "Mine historique",
    ("historic", "mine_shaft"): "Puits de mine",
    ("historic", "wreck"): "Épave historique",
    ("historic", "cannon"): "Canon historique",
    ("historic", "ship"): "Navire historique",
    ("historic", "aircraft"): "Aéronef historique",
    # archaeological_site
    ("archaeological_site", "tumulus"): "Tumulus",
    ("archaeological_site", "petroglyph"): "Pétroglyphe",
    ("archaeological_site", "megalith"): "Mégalithe",
    ("archaeological_site", "dolmen"): "Dolmen",
    ("archaeological_site", "menhir"): "Menhir",
    ("archaeological_site", "settlement"): "Site d'habitat ancien",
    ("archaeological_site", "necropolis"): "Nécropole",
    ("archaeological_site", "fortification"): "Fortification ancienne",
    ("archaeological_site", "temple"): "Temple antique",
    ("archaeological_site", "theatre"): "Théâtre antique",
    ("archaeological_site", "amphitheatre"): "Amphithéâtre",
    ("archaeological_site", "bath"): "Thermes antiques",
    ("archaeological_site", "city"): "Cité antique",
    ("archaeological_site", "villa"): "Villa antique",
    ("archaeological_site", "hypogeum"): "Hypogée",
    ("archaeological_site", "catacomb"): "Catacombe",
    ("archaeological_site", "rock_cut_tomb"): "Tombeau rupestre",
    ("archaeological_site", "tell"): "Tell archéologique",
    ("archaeological_site", "pyramid"): "Pyramide",
    ("archaeological_site", "obelisk"): "Obélisque",
    # leisure
    ("leisure", "park"): "Parc",
    ("leisure", "garden"): "Jardin",
    ("leisure", "sports_centre"): "Centre sportif",
    ("leisure", "swimming_pool"): "Piscine",
    ("leisure", "playground"): "Aire de jeux",
    ("leisure", "stadium"): "Stade",
    ("leisure", "golf_course"): "Terrain de golf",
    ("leisure", "fitness_centre"): "Salle de sport",
    ("leisure", "track"): "Piste sportive",
    ("leisure", "ice_rink"): "Patinoire",
    ("leisure", "marina"): "Marina",
    ("leisure", "water_park"): "Parc aquatique",
    ("leisure", "nature_reserve"): "Réserve naturelle",
    ("leisure", "picnic_table"): "Aire de pique-nique",
    ("leisure", "dog_park"): "Parc à chiens",
    ("leisure", "amusement_arcade"): "Salle de jeux",
    ("leisure", "bowling_alley"): "Bowling",
    ("leisure", "dance"): "Salle de danse",
    ("leisure", "hackerspace"): "Hackerspace",
    ("leisure", "sauna"): "Sauna",
    ("leisure", "slipway"): "Cale de mise à l'eau",
    ("leisure", "sports_hall"): "Salle de sport",
    # sport
    ("sport", "swimming"): "Piscine / Natation",
    ("sport", "soccer"): "Terrain de football",
    ("sport", "tennis"): "Court de tennis",
    ("sport", "basketball"): "Terrain de basket-ball",
    ("sport", "handball"): "Terrain de handball",
    ("sport", "volleyball"): "Terrain de volley-ball",
    ("sport", "athletics"): "Piste d'athlétisme",
    ("sport", "equestrian"): "Centre équestre",
    ("sport", "golf"): "Golf",
    ("sport", "skiing"): "Ski",
    ("sport", "multi"): "Terrain multisports",
    # natural
    ("natural", "peak"): "Sommet",
    ("natural", "cave_entrance"): "Grotte",
    ("natural", "beach"): "Plage",
    ("natural", "waterfall"): "Cascade",
    ("natural", "volcano"): "Volcan",
    ("natural", "bay"): "Baie",
    ("natural", "cape"): "Cap",
    ("natural", "cliff"): "Falaise",
    ("natural", "rock"): "Rocher",
    ("natural", "stone"): "Pierre",
    ("natural", "sinkhole"): "Doline",
    ("natural", "spring"): "Source",
    ("natural", "hot_spring"): "Source chaude",
    ("natural", "geyser"): "Geyser",
    ("natural", "valley"): "Vallée",
    ("natural", "ridge"): "Crête",
    ("natural", "gorge"): "Gorge",
    ("natural", "desert"): "Désert",
    ("natural", "sand"): "Étendue de sable",
    ("natural", "dune"): "Dune",
    ("natural", "oasis"): "Oasis",
    ("natural", "tree"): "Arbre remarquable",
    ("natural", "wood"): "Bois / Forêt",
    ("natural", "grassland"): "Prairie",
    ("natural", "heath"): "Landes",
    ("natural", "scrub"): "Maquis",
    ("natural", "wetland"): "Zone humide",
    ("natural", "marsh"): "Marais",
    ("natural", "lake"): "Lac",
    ("natural", "pond"): "Étang",
    ("natural", "reservoir"): "Réservoir d'eau",
    ("natural", "river"): "Rivière",
    ("natural", "stream"): "Ruisseau",
    ("natural", "glacier"): "Glacier",
    ("natural", "isthmus"): "Isthme",
    ("natural", "peninsula"): "Péninsule",
    ("natural", "plateau"): "Plateau",
    ("natural", "plain"): "Plaine",
    ("natural", "reef"): "Récif",
    ("natural", "shoal"): "Haut-fond",
    ("natural", "strait"): "Détroit",
    ("natural", "fjord"): "Fjord",
    # tourism
    ("tourism", "viewpoint"): "Point de vue panoramique",
    ("tourism", "information"): "Office de tourisme",
    ("tourism", "attraction"): "Attraction touristique",
    ("tourism", "picnic_site"): "Aire de pique-nique",
    ("tourism", "artwork"): "Œuvre d'art",
    ("tourism", "apartment"): "Appartement touristique",
    ("tourism", "chalet"): "Chalet",
    ("tourism", "guest_house"): "Maison d'hôtes",
    ("tourism", "hotel"): "Hôtel",
    ("tourism", "hostel"): "Auberge",
    ("tourism", "motel"): "Motel",
    ("tourism", "camp_site"): "Camping",
    ("tourism", "caravan_site"): "Camping-car",
    ("tourism", "wilderness"): "Hébergement nature",
    ("tourism", "alpine_hut"): "Refuge de montagne",
    ("tourism", "museum"): "Musée",
    ("tourism", "theme_park"): "Parc d'attractions",
    ("tourism", "zoo"): "Zoo",
    ("tourism", "aquarium"): "Aquarium",
    ("tourism", "gallery"): "Galerie d'art",
    # building
    ("building", "mosque"): "Mosquée",
    ("building", "church"): "Église",
    ("building", "cathedral"): "Cathédrale",
    ("building", "chapel"): "Chapelle",
    ("building", "temple"): "Temple",
    ("building", "synagogue"): "Synagogue",
    ("building", "shrine"): "Sanctuaire",
    ("building", "monastery"): "Monastère",
    ("building", "convent"): "Couvent",
    ("building", "castle"): "Château",
    ("building", "tower"): "Tour",
    ("building", "ruins"): "Ruines",
    ("building", "public"): "Bâtiment public",
    ("building", "civic"): "Bâtiment civique",
    ("building", "government"): "Bâtiment gouvernemental",
    ("building", "museum"): "Bâtiment muséal",
    ("building", "school"): "Bâtiment scolaire",
    ("building", "university"): "Bâtiment universitaire",
    ("building", "hospital"): "Bâtiment hospitalier",
    ("building", "train_station"): "Gare ferroviaire",
    ("building", "bunker"): "Bunker",
    ("building", "shed"): "Hangar",
    ("building", "garage"): "Garage",
    ("building", "warehouse"): "Entrepôt",
    ("building", "office"): "Immeuble de bureaux",
    ("building", "retail"): "Magasin",
    ("building", "commercial"): "Bâtiment commercial",
    ("building", "industrial"): "Bâtiment industriel",
    ("building", "farm"): "Ferme",
    ("building", "greenhouse"): "Serre",
    # ruins
    ("ruins", "yes"): "Ruines",
    ("ruins", "building"): "Ruines d'un bâtiment",
    ("ruins", "castle"): "Ruines d'un château",
    ("ruins", "church"): "Ruines d'une église",
    ("ruins", "fort"): "Ruines d'un fort",
    ("ruins", "tower"): "Ruines d'une tour",
    ("ruins", "aqueduct"): "Ruines d'un aqueduc",
    ("ruins", "bridge"): "Ruines d'un pont",
    ("ruins", "wall"): "Ruines d'un mur",
    ("ruins", "theatre"): "Ruines d'un théâtre",
    ("ruins", "bath"): "Ruines de thermes",
    ("ruins", "temple"): "Ruines d'un temple",
    ("ruins", "mosque"): "Ruines d'une mosquée",
})

# ── Tag value → descriptive label (EN) ──
TAG_EN = defaultdict(lambda: None, {
    ("shop", "bakery"): "Bakery",
    ("shop", "confectionery"): "Confectionery",
    ("shop", "supermarket"): "Supermarket",
    ("shop", "gift"): "Gift Shop",
    ("shop", "souvenir"): "Souvenir Shop",
    ("shop", "books"): "Bookstore",
    ("amenity", "cafe"): "Cafe",
    ("amenity", "bar"): "Bar",
    ("amenity", "restaurant"): "Restaurant",
    ("amenity", "fast_food"): "Fast Food",
    ("amenity", "public_bath"): "Public Bath / Hammam",
    ("amenity", "library"): "Library",
    ("amenity", "internet_cafe"): "Cybercafe",
    ("amenity", "pharmacy"): "Pharmacy",
    ("amenity", "marketplace"): "Marketplace",
    ("man_made", "tower"): "Tower",
    ("man_made", "water_tower"): "Water Tower",
    ("man_made", "lighthouse"): "Lighthouse",
    ("tower:type", "communication"): "Communication Tower",
    ("tower:type", "watchtower"): "Watchtower",
    ("tower:type", "minaret"): "Minaret",
    ("tower:type", "observation"): "Observation Tower",
    ("tower:type", "defensive"): "Defensive Tower",
    ("historic", "archaeological_site"): "Archaeological Site",
    ("historic", "ruins"): "Historic Ruins",
    ("historic", "memorial"): "Memorial",
    ("historic", "monument"): "Historic Monument",
    ("historic", "castle"): "Historic Castle",
    ("historic", "fort"): "Historic Fort",
    ("archaeological_site", "tumulus"): "Tumulus",
    ("archaeological_site", "petroglyph"): "Petroglyph",
    ("leisure", "park"): "Park",
    ("leisure", "garden"): "Garden",
    ("leisure", "sports_centre"): "Sports Center",
    ("leisure", "swimming_pool"): "Swimming Pool",
    ("leisure", "stadium"): "Stadium",
    ("sport", "swimming"): "Swimming Pool",
    ("natural", "peak"): "Peak / Summit",
    ("natural", "cave_entrance"): "Cave",
    ("natural", "beach"): "Beach",
    ("natural", "waterfall"): "Waterfall",
    ("natural", "volcano"): "Volcano",
    ("natural", "bay"): "Bay",
    ("natural", "cape"): "Cape",
    ("natural", "cliff"): "Cliff",
    ("natural", "spring"): "Spring",
    ("natural", "hot_spring"): "Hot Spring",
    ("natural", "lake"): "Lake",
    ("natural", "dune"): "Dune",
    ("natural", "oasis"): "Oasis",
    ("tourism", "viewpoint"): "Panoramic Viewpoint",
    ("tourism", "information"): "Tourist Information",
    ("tourism", "attraction"): "Tourist Attraction",
    ("tourism", "picnic_site"): "Picnic Site",
    ("tourism", "artwork"): "Artwork",
    ("tourism", "museum"): "Museum",
    ("building", "mosque"): "Mosque",
    ("building", "church"): "Church",
    ("building", "cathedral"): "Cathedral",
    ("building", "castle"): "Castle",
    ("ruins", "yes"): "Ruins",
})

CATEGORY_FALLBACKS_FR = {
    "historical": "Site historique algérien",
    "natural": "Site naturel à découvrir",
    "cultural": "Patrimoine culturel algérien",
    "religious": "Lieu religieux",
    "museum": "Musée",
    "beach": "Plage",
    "mountain": "Sommet montagneux",
    "park": "Parc / espace vert",
    "market": "Marché local",
    "restaurant": "Restauration sur place",
    "cafe": "Café / salon de thé",
    "other": "Point d'intérêt local",
}

CATEGORY_FALLBACKS_EN = {
    "historical": "Algerian historical site",
    "natural": "Natural site to discover",
    "cultural": "Algerian cultural heritage",
    "religious": "Religious site",
    "museum": "Museum",
    "beach": "Beach",
    "mountain": "Mountain summit",
    "park": "Park / green space",
    "market": "Local market",
    "restaurant": "Dining",
    "cafe": "Cafe / tea room",
    "other": "Local point of interest",
}

TYPE_LABELS = {
    "archaeological_site": "Site archéologique",
    "monument": "Monument historique",
    "memorial": "Mémorial",
    "ruins": "Ruines historiques",
    "castle": "Château historique",
    "fort": "Fort historique",
    "battlefield": "Champ de bataille historique",
    "museum": "Musée",
    "artwork": "Œuvre d'art",
    "attraction": "Attraction touristique",
    "viewpoint": "Point de vue panoramique",
    "peak": "Sommet",
    "beach": "Plage",
    "cave": "Grotte",
    "waterfall": "Cascade",
    "volcano": "Volcan",
    "bay": "Baie",
    "park": "Parc",
    "garden": "Jardin",
    "nature_reserve": "Réserve naturelle",
    "restaurant": "Restaurant",
    "cafe": "Café",
    "fast_food": "Restauration rapide",
    "pub": "Pub",
    "bar": "Bar",
    "place_of_worship": "Lieu de culte",
    "library": "Bibliothèque",
    "theatre": "Théâtre",
    "cinema": "Cinéma",
    "supermarket": "Supermarché",
    "mall": "Centre commercial",
    "stadium": "Stade",
    "sports_centre": "Centre sportif",
    "marina": "Marina",
    "lighthouse": "Phare",
    "tower": "Tour",
    "observatory": "Observatoire",
}


def get_tag_label(osm_tags, tag_map):
    """Return label from first matching tag key+value."""
    for key, val in osm_tags.items():
        label = tag_map.get((key, val))
        if label:
            return label
        # try value as key for reverse lookup (e.g. "archaeological_site" key with value "tumulus")
        label = tag_map.get((val, "yes"))
        if label:
            return label
    return None


def generate_descs(row):
    """Generate (desc_fr, desc_en) for a POI row."""
    subtype = row.get("subtype") or ""
    osm_tags = row.get("osm_tags") or {}
    name = row.get("name") or ""
    category = row.get("category") or ""
    commune = row.get("commune") or ""
    wilaya_name = row.get("wilaya_name") or ""

    is_unnamed = "(non nommé)" in name or name.lower().startswith("unknown")

    parts_fr = []
    parts_en = []

    # 1. Subtype label
    label_fr = TYPE_LABELS.get(subtype)
    if label_fr:
        parts_fr.append(label_fr)

    # 2. Tag value label (most specific)
    tag_label_fr = get_tag_label(osm_tags, TAG_FR)
    if tag_label_fr:
        parts_fr.append(tag_label_fr)

    tag_label_en = get_tag_label(osm_tags, TAG_EN)
    if tag_label_en:
        parts_en.append(tag_label_en)

    # 3. Location
    location_parts_fr = []
    if commune:
        location_parts_fr.append(commune)
    elif wilaya_name:
        location_parts_fr.append(wilaya_name)
    loc_fr = f"à {' - '.join(location_parts_fr)}" if location_parts_fr else ""

    location_parts_en = []
    if commune:
        location_parts_en.append(commune)
    elif wilaya_name:
        location_parts_en.append(wilaya_name)
    loc_en = f"in {' - '.join(location_parts_en)}" if location_parts_en else ""

    if loc_fr:
        parts_fr.append(loc_fr)
    if loc_en:
        parts_en.append(loc_en)

    # 4. Civilization / period
    civ = osm_tags.get("historic:civilization") or osm_tags.get("historic_civilization")
    period = osm_tags.get("historic:period") or osm_tags.get("historic:era")
    if civ:
        parts_fr.append(f"Civilisation {civ}")
        parts_en.append(f"{civ} civilization")
    if period:
        parts_fr.append(f"Période {period}")
        parts_en.append(f"{period} period")

    # 5. Elevation
    ele = osm_tags.get("ele")
    if ele and (subtype == "peak" or category == "mountain"):
        try:
            ele_str = f"{int(float(ele))}m"
        except ValueError:
            ele_str = f"{ele}m"
        parts_fr.append(f"Altitude {ele_str}")
        parts_en.append(f"Elevation {ele_str}")

    # 6. OSM description or note
    osm_desc = osm_tags.get("description") or osm_tags.get("note")
    if osm_desc and len(osm_desc) > 5:
        parts_fr.append(osm_desc)
        parts_en.append(osm_desc)

    # 7. Fallback by category (only if nothing specific found)
    if not parts_fr or len(parts_fr) <= 1:
        fallback_fr = CATEGORY_FALLBACKS_FR.get(category)
        if fallback_fr and not civ and not period:
            parts_fr.append(fallback_fr)

    if not parts_en or len(parts_en) <= 1:
        fallback_en = CATEGORY_FALLBACKS_EN.get(category)
        if fallback_en:
            parts_en.append(fallback_en)

    # 8. Opening hours
    opening = osm_tags.get("opening_hours") or row.get("opening_hours") or ""
    if opening and not is_unnamed:
        parts_fr.append(f"Horaires: {opening}")
        parts_en.append(f"Hours: {opening}")

    # Deduplicate sequential identical entries
    deduped_fr = []
    for p in parts_fr:
        if p and (not deduped_fr or p != deduped_fr[-1]):
            deduped_fr.append(p)

    deduped_en = []
    for p in parts_en:
        if p and (not deduped_en or p != deduped_en[-1]):
            deduped_en.append(p)

    desc_fr = " - ".join(deduped_fr) if deduped_fr else None
    desc_en = " - ".join(deduped_en) if deduped_en else None

    return desc_fr, desc_en


def main():
    print("=== Enrich remaining descriptions (all POIs) ===\n")

    engine = create_engine(DATABASE_URL)

    # Load wilaya name mapping
    wilaya_names = {}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name_fr FROM wilayas")).fetchall()
        for r in rows:
            wilaya_names[r[0]] = r[1]
    print(f"Wilayas loaded: {len(wilaya_names)}")

    # Query all POIs without descriptions
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT p.id, p.name, p.category, p.subtype, p.commune, p.opening_hours, p.osm_tags, p.wilaya_id
                FROM pois p
                WHERE (p.description IS NULL OR p.description = '')
            """)
        ).mappings().fetchall()
        print(f"POIs needing description: {len(rows)}")

    updated = 0
    skipped = 0
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            row_dict = dict(row)
            row_dict["wilaya_name"] = wilaya_names.get(row_dict.get("wilaya_id"), "")

            desc_fr, desc_en = generate_descs(row_dict)

            if desc_fr:
                conn.execute(
                    text("UPDATE pois SET description = :desc WHERE id = :pid"),
                    {"desc": desc_fr, "pid": row_dict["id"]},
                )
                updated += 1
            else:
                skipped += 1

            if (i + 1) % 1000 == 0:
                print(f"  {i+1}/{len(rows)} processed ({updated} updated, {skipped} skipped)", end="\r")
                sys.stdout.flush()

    print(f"\n\nResults: {updated} updated, {skipped} skipped (no tags to generate from)")

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM pois")).scalar()
        with_desc = conn.execute(
            text("SELECT COUNT(*) FROM pois WHERE description IS NOT NULL AND description != ''")
        ).scalar()

    print(f"\nFinal: {with_desc}/{total} ({with_desc/total*100:.1f}%) have descriptions")
    print("Done!")


if __name__ == "__main__":
    main()
