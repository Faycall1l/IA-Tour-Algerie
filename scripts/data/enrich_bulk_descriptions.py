#!/usr/bin/env python3
"""Bulk-enrich descriptions for the 73K Overpass-sourced POIs from their osm_tags.

No external API calls — purely deterministic tag→description mapping.
Updates in batches of 500 rows, commits every 5000.
"""

import asyncio
import json
from collections import defaultdict

from app.db.session import async_session
from sqlalchemy import text

# ── Tag value → short FR description ──
TAG_FR = defaultdict(lambda: None, {
    ("shop", "bakery"): "Boulangerie",
    ("shop", "confectionery"): "Confiserie",
    ("shop", "supermarket"): "Supermarché",
    ("shop", "gift"): "Boutique de cadeaux",
    ("shop", "souvenir"): "Boutique de souvenirs",
    ("shop", "mall"): "Centre commercial",
    ("shop", "books"): "Librairie",
    ("shop", "clothes"): "Magasin de vêtements",
    ("shop", "art"): "Galerie d'art",
    ("shop", "jewelry"): "Bijouterie",
    ("shop", "car"): "Concessionnaire automobile",
    ("shop", "car_repair"): "Garage automobile",
    ("shop", "hairdresser"): "Salon de coiffure",
    ("shop", "beauty"): "Institut de beauté",
    ("shop", "travel_agency"): "Agence de voyages",
    ("shop", "convenience"): "Épicerie",
    ("shop", "department_store"): "Grand magasin",
    ("shop", "hardware"): "Quincaillerie",
    ("shop", "electronics"): "Magasin d'électronique",
    ("shop", "furniture"): "Magasin de meubles",
    ("shop", "sports"): "Magasin de sport",
    ("shop", "mobile_phone"): "Téléphonie mobile",
    ("shop", "craft"): "Boutique d'artisanat",
    ("shop", "pottery"): "Atelier de poterie",
    ("shop", "carpet"): "Tapisserie",
    ("shop", "leather"): "Maroquinerie",
    ("shop", "curtain"): "Mercerie",
    ("shop", "florist"): "Fleuriste",
    ("shop", "pastry"): "Pâtisserie",
    ("shop", "greengrocer"): "Fruits et légumes",
    ("shop", "butcher"): "Boucherie",
    ("shop", "wine"): "Cave à vin",
    ("shop", "optician"): "Opticien",
    ("shop", "chemist"): "Pharmacie",
    ("shop", "tobacco"): "Marchand de tabac",
    ("shop", "kiosk"): "Kiosque",
    ("shop", "stationery"): "Papeterie",
    ("shop", "bicycle"): "Magasin de vélos",
    ("shop", "variety_store"): "Bazar",
    ("shop", "dry_cleaning"): "Nettoyage à sec",
    ("shop", "laundry"): "Blanchisserie",
    ("shop", "pet"): "Animalerie",
    ("shop", "funeral_directors"): "Pompes funèbres",
    ("shop", "outdoor"): "Magasin de plein air",
    ("shop", "diy"): "Magasin de bricolage",
    ("shop", "garden_centre"): "Jardinerie",
    ("shop", "tyres"): "Pneumatiques",
    # craft
    ("craft", "jeweler"): "Artisan bijoutier",
    ("craft", "carpenter"): "Menuisier",
    ("craft", "metal"): "Métallurgiste",
    ("craft", "pottery"): "Potier",
    ("craft", "tailor"): "Tailleur",
    ("craft", "shoemaker"): "Cordonnier",
    ("craft", "weaver"): "Tisserand",
    ("craft", "glass"): "Verrier",
    ("craft", "stonemason"): "Tailleur de pierre",
    ("craft", "printer"): "Imprimeur",
    # amenity
    ("amenity", "cafe"): "Café",
    ("amenity", "bar"): "Bar",
    ("amenity", "restaurant"): "Restaurant",
    ("amenity", "fast_food"): "Restauration rapide",
    ("amenity", "library"): "Bibliothèque",
    ("amenity", "internet_cafe"): "Cybercafé",
    ("amenity", "public_bath"): "Hammam",
    ("amenity", "pharmacy"): "Pharmacie",
    ("amenity", "bank"): "Banque",
    ("amenity", "post_office"): "Bureau de poste",
    ("amenity", "place_of_worship"): "Lieu de culte",
    ("amenity", "school"): "École",
    ("amenity", "university"): "Université",
    ("amenity", "hospital"): "Hôpital",
    ("amenity", "clinic"): "Clinique",
    ("amenity", "police"): "Commissariat de police",
    ("amenity", "townhall"): "Mairie",
    ("amenity", "community_centre"): "Centre communautaire",
    ("amenity", "cinema"): "Cinéma",
    ("amenity", "theatre"): "Théâtre",
    ("amenity", "fountain"): "Fontaine",
    ("amenity", "drinking_water"): "Point d'eau potable",
    ("amenity", "fuel"): "Station-service",
    ("amenity", "car_wash"): "Lavage auto",
    ("amenity", "parking"): "Parking",
    ("amenity", "bench"): "Banc public",
    ("amenity", "toilets"): "Toilettes publiques",
    ("amenity", "shelter"): "Abri",
    # tourism
    ("tourism", "museum"): "Musée",
    ("tourism", "attraction"): "Site touristique",
    ("tourism", "viewpoint"): "Point de vue",
    ("tourism", "information"): "Point d'information touristique",
    ("tourism", "picnic_site"): "Aire de pique-nique",
    ("tourism", "camp_site"): "Camping",
    ("tourism", "theme_park"): "Parc de loisirs",
    ("tourism", "zoo"): "Zoo",
    ("tourism", "gallery"): "Galerie d'art",
    ("tourism", "hostel"): "Auberge de jeunesse",
    ("tourism", "hotel"): "Hôtel",
    ("tourism", "motel"): "Motel",
    ("tourism", "guest_house"): "Maison d'hôtes",
    ("tourism", "chalet"): "Chalet",
    ("tourism", "apartment"): "Appartement de vacances",
    ("tourism", "resort"): "Station balnéaire",
    ("tourism", "wilderness_hut"): "Cabane de montagne",
    # historic
    ("historic", "castle"): "Château",
    ("historic", "ruins"): "Ruines",
    ("historic", "archaeological_site"): "Site archéologique",
    ("historic", "memorial"): "Mémorial",
    ("historic", "monument"): "Monument historique",
    ("historic", "fort"): "Fort",
    ("historic", "mosque"): "Mosquée historique",
    ("historic", "mausoleum"): "Mausolée",
    ("historic", "tomb"): "Tombeau",
    ("historic", "church"): "Église historique",
    ("historic", "palace"): "Palais",
    ("historic", "citywalls"): "Remparts",
    ("historic", "yes"): "Site historique",
    ("historic", "house"): "Maison historique",
    ("historic", "manor"): "Manoir",
    ("historic", "tower"): "Tour historique",
    ("historic", "bridge"): "Pont historique",
    ("historic", "wayside_cross"): "Croix de chemin",
    ("historic", "battlefield"): "Champ de bataille",
    # natural
    ("natural", "peak"): "Sommet",
    ("natural", "hill"): "Colline",
    ("natural", "volcano"): "Volcan",
    ("natural", "cliff"): "Falaise",
    ("natural", "dune"): "Dune",
    ("natural", "ridge"): "Crête",
    ("natural", "waterfall"): "Cascade",
    ("natural", "spring"): "Source",
    ("natural", "hot_spring"): "Source chaude / Hammam naturel",
    ("natural", "cave"): "Grotte",
    ("natural", "oasis"): "Oasis",
    ("natural", "lake"): "Lac",
    ("natural", "water"): "Plan d'eau",
    ("natural", "wood"): "Forêt / Bois",
    ("natural", "beach"): "Plage",
    ("natural", "cape"): "Cap",
    ("natural", "bay"): "Baie",
    ("natural", "scrub"): "Maquis",
    ("natural", "grassland"): "Prairie",
    ("natural", "bare_rock"): "Rochers",
    ("natural", "sand"): "Étendue de sable",
    ("natural", "wetland"): "Zone humide",
    ("natural", "glacier"): "Glacier",
    ("natural", "yes"): "Site naturel",
    # leisure
    ("leisure", "park"): "Parc",
    ("leisure", "garden"): "Jardin",
    ("leisure", "nature_reserve"): "Réserve naturelle",
    ("leisure", "swimming_pool"): "Piscine",
    ("leisure", "sports_centre"): "Centre sportif",
    ("leisure", "stadium"): "Stade",
    ("leisure", "playground"): "Aire de jeux",
    ("leisure", "track"): "Piste d'athlétisme",
    ("leisure", "pitch"): "Terrain de sport",
    ("leisure", "fitness_centre"): "Salle de sport",
    ("leisure", "water_park"): "Parc aquatique",
    # man_made
    ("man_made", "lighthouse"): "Phare",
    ("man_made", "tower"): "Tour",
    ("man_made", "bridge"): "Pont",
    ("man_made", "windmill"): "Moulin à vent",
    ("man_made", "obelisk"): "Obélisque",
    ("man_made", "monument"): "Monument",
    ("man_made", "communications_tower"): "Tour de communication",
    ("man_made", "minaret"): "Minaret",
    ("man_made", "dam"): "Barrage",
    ("man_made", "water_tower"): "Château d'eau",
    ("man_made", "silo"): "Silo",
    ("man_made", "mast"): "Mât",
    # waterway
    ("waterway", "waterfall"): "Cascade",
    ("waterway", "dam"): "Barrage",
    ("waterway", "weir"): "Seuil hydraulique",
    # place
    ("place", "city"): "Ville",
    ("place", "town"): "Ville",
    ("place", "village"): "Village",
    ("place", "hamlet"): "Hameau",
    ("place", "suburb"): "Quartier",
    ("place", "neighbourhood"): "Quartier",
    ("place", "locality"): "Lieu-dit",
    ("place", "square"): "Place",
    ("place", "island"): "Île",
    # building
    ("building", "yes"): "Bâtiment",
    ("building", "mosque"): "Mosquée",
    ("building", "church"): "Église",
    ("building", "house"): "Maison",
    ("building", "apartments"): "Immeuble d'habitation",
    ("building", "commercial"): "Bâtiment commercial",
    ("building", "industrial"): "Bâtiment industriel",
    ("building", "public"): "Bâtiment public",
    ("building", "hotel"): "Hôtel",
    ("building", "train_station"): "Gare",
})

# ── Tag value → short EN description ──
TAG_EN = defaultdict(lambda: None, {
    ("tourism", "museum"): "Museum",
    ("tourism", "attraction"): "Tourist attraction",
    ("tourism", "viewpoint"): "Scenic viewpoint",
    ("tourism", "information"): "Tourist information point",
    ("tourism", "picnic_site"): "Picnic site",
    ("tourism", "camp_site"): "Campsite",
    ("tourism", "hotel"): "Hotel",
    ("tourism", "hostel"): "Hostel",
    ("tourism", "guest_house"): "Guest house",
    ("tourism", "gallery"): "Art gallery",
    ("historic", "castle"): "Castle",
    ("historic", "ruins"): "Ruins",
    ("historic", "archaeological_site"): "Archaeological site",
    ("historic", "memorial"): "Memorial",
    ("historic", "monument"): "Historic monument",
    ("historic", "fort"): "Fort",
    ("historic", "mosque"): "Historic mosque",
    ("historic", "mausoleum"): "Mausoleum",
    ("historic", "tomb"): "Tomb",
    ("historic", "church"): "Historic church",
    ("historic", "palace"): "Palace",
    ("historic", "citywalls"): "City walls",
    ("natural", "peak"): "Mountain peak",
    ("natural", "waterfall"): "Waterfall",
    ("natural", "spring"): "Spring",
    ("natural", "hot_spring"): "Hot spring",
    ("natural", "cave"): "Cave",
    ("natural", "oasis"): "Oasis",
    ("natural", "lake"): "Lake",
    ("natural", "beach"): "Beach",
    ("natural", "dune"): "Dune",
    ("natural", "cape"): "Cape",
    ("natural", "cliff"): "Cliff",
    ("natural", "wood"): "Forest",
    ("amenity", "restaurant"): "Restaurant",
    ("amenity", "cafe"): "Cafe",
    ("amenity", "bar"): "Bar",
    ("amenity", "place_of_worship"): "Place of worship",
    ("amenity", "cinema"): "Cinema",
    ("amenity", "theatre"): "Theatre",
    ("leisure", "park"): "Park",
    ("leisure", "garden"): "Garden",
    ("leisure", "nature_reserve"): "Nature reserve",
    ("leisure", "stadium"): "Stadium",
    ("shop", "craft"): "Craft shop",
    ("shop", "souvenir"): "Souvenir shop",
})


def generate_description(tags: dict, name: str, category: str, subtype: str) -> tuple[str, str]:
    """Generate FR and EN descriptions from OSM tags."""
    parts_fr = []
    parts_en = []

    # Primary tag label
    for key in ("tourism", "historic", "natural", "amenity", "leisure",
                "shop", "craft", "man_made", "waterway", "place", "building"):
        val = tags.get(key)
        if val:
            fr = TAG_FR.get((key, val))
            en = TAG_EN.get((key, val))
            if fr:
                parts_fr.append(fr)
            elif val.replace("_", " ").istitle():
                parts_fr.append(val.replace("_", " ").title())
            else:
                parts_fr.append(val.replace("_", " ").capitalize())
            if en:
                parts_en.append(en)
            break

    # Build description from tags
    locality = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")
    street = tags.get("addr:street")
    if locality:
        parts_fr.append(f"situé à {locality}")
        parts_en.append(f"located in {locality}")

    cuisine = tags.get("cuisine")
    if cuisine:
        parts_fr.append(f"servant de la cuisine {cuisine.replace(';', ', ')}")
        parts_en.append(f"serving {cuisine.replace(';', ', ')} cuisine")

    phone = tags.get("phone") or tags.get("contact:phone")
    if phone:
        parts_fr.append(f"Tél: {phone}")
        parts_en.append(f"Tel: {phone}")

    website = tags.get("website") or tags.get("contact:website")
    if website:
        parts_fr.append(f"Site: {website}")
        parts_en.append(f"Web: {website}")

    opening = tags.get("opening_hours")
    if opening and len(opening) < 60:
        parts_fr.append(f"Horaires: {opening}")
        parts_en.append(f"Hours: {opening}")

    fee = tags.get("fee")
    if fee == "yes":
        parts_fr.append("Entrée payante")
        parts_en.append("Paid entry")
    elif fee == "no":
        parts_fr.append("Entrée gratuite")
        parts_en.append("Free entry")

    wheelchair = tags.get("wheelchair")
    if wheelchair == "yes":
        parts_fr.append("Accessible aux personnes à mobilité réduite")
        parts_en.append("Wheelchair accessible")

    if street:
        addr = f"{street}"
        number = tags.get("addr:housenumber")
        if number:
            addr = f"{number} {street}"
        parts_fr.append(addr)
        parts_en.append(addr)

    if not parts_fr:
        fr_desc = f"{name} — {category}/{subtype}"
    else:
        fr_desc = name + ", " + ", ".join(parts_fr)

    if not parts_en:
        en_desc = f"{name} — {category}/{subtype}"
    else:
        en_desc = name + ", " + ", ".join(parts_en)

    # Cap length
    if len(fr_desc) > 500:
        fr_desc = fr_desc[:497] + "..."
    if len(en_desc) > 500:
        en_desc = en_desc[:497] + "..."

    return fr_desc, en_desc


async def main():
    batch_size = 500
    commit_every = 5000
    total_updated = 0
    batch = []

    async with async_session() as db:
        # Fetch all POIs without descriptions that have osm_tags
        result = await db.execute(text("""
            SELECT id, name, category, subtype, osm_tags
            FROM pois
            WHERE (description IS NULL OR description = '')
              AND osm_tags IS NOT NULL
              AND osm_tags != 'null'::jsonb
        """))
        rows = result.fetchall()
        print(f"Found {len(rows)} POIs to enrich", flush=True)

        for _i, (poi_id, name, category, subtype, osm_tags) in enumerate(rows):
            if isinstance(osm_tags, str):
                try:
                    tags = json.loads(osm_tags)
                except json.JSONDecodeError:
                    tags = {}
            elif isinstance(osm_tags, dict):
                tags = osm_tags
            else:
                tags = {}

            if not tags:
                # Minimal fallback from category/subtype
                fallback = (subtype or category or "lieu").replace("_", " ").capitalize()
                batch.append({
                    "id": poi_id,
                    "description": f"{name or fallback} — {fallback}",
                })
            else:
                fr, en = generate_description(tags, name or (subtype or "POI"), category, subtype)
                batch.append({
                    "id": poi_id,
                    "description": fr,
                })

            if len(batch) >= batch_size:
                await _flush(db, batch)
                total_updated += len(batch)
                batch = []
                if total_updated % commit_every == 0:
                    await db.commit()
                    print(f"  {total_updated}/{len(rows)} done", flush=True)

        if batch:
            await _flush(db, batch)
            total_updated += len(batch)
        await db.commit()

    print(f"\nTotal enriched: {total_updated} POIs", flush=True)


async def _flush(db, batch):
    for item in batch:
        await db.execute(
            text("UPDATE pois SET description = :desc WHERE id = :id"),
            {"desc": item["description"], "id": item["id"]},
        )


if __name__ == "__main__":
    asyncio.run(main())
