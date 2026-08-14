"""PagesMaghreb artisan import: craft classifier + corpus transform logic."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from scripts.data.classify_pm_crafts import classify_categories  # noqa: E402
from scripts.data.import_pagesmaghreb import normalize_name, transform  # noqa: E402

# --- craft classifier ------------------------------------------------------


@pytest.mark.parametrize(
    "categories,expected",
    [
        (["Bijouterie (entreprise artisanale)"], "jewelry"),
        (["Bijouterie horlogerie", "Bijouterie fantaisie (détail)"], "jewelry"),
        (["Céramiques d'art", "Céramique (artisanat)"], "pottery"),
        (["Poterie"], "pottery"),
        (["Carreaux céramiques"], "tilework"),
        (["Tapis (fabrication)"], "carpet_weaving"),
        (["Moquettes, tapis (détail)"], "carpet_weaving"),
        (["Broderies (artisanat)"], "embroidery"),
        (["Maroquinerie traditionnelle (détail)"], "leather_work"),
        (["Travail du cuir"], "leather_work"),
        (["Ebénisterie"], "woodwork"),
        (["Ferronnerie d'art"], "metalwork"),
        (["Cuivrerie et dinanderie"], "copper_work"),
        (["Verrerie d'art, verrerie soufflée (fabrication, gros)"], "glasswork"),
        (["Vannerie (fabrication)"], "basket_weaving"),
        (["Couture (haute couture, création)"], "textile"),
        (["Vêtements pour femmes (détail)"], "textile"),
        (["Artisanat d'art"], "other"),
        (["Artisanat (détail)", "Artisanat d'art"], "other"),
        (["Galeries d'art"], "other"),
        # Exact override beats keyword fallback: corail is jewelry not "other".
        (["Corail (Fabrication)"], "jewelry"),
        # Mosaïques -> tilework (exact override), not pottery.
        (["Mosaïques et céramiques"], "tilework"),
        # Mixed craft + supply keeps the craft.
        (["Céramiques (fabrication)", "Céramiques : matériel et fournitures"], "pottery"),
    ],
)
def test_classify_categories(categories, expected):
    assert classify_categories(categories) == expected


@pytest.mark.parametrize(
    "categories",
    [
        # Supply-only shop (no workshop).
        ["Artisanat et travaux manuels : fournitures (détail)"],
        ["Décoration : matériel et fournitures"],
        # Construction / trades — not artisan work.
        ["Bâtiment (entreprises)"],
        ["Garages d'automobiles, réparation"],
        ["Compresseurs"],
        ["Electroménager (détail)"],
        # Empty / no categories.
        [],
        [""],
    ],
)
def test_classify_categories_excludes(categories):
    assert classify_categories(categories) is None


def test_classify_categories_wholesale_only_excluded():
    """Wholesale-only (not visitable) is excluded; adding a retail craft keeps it."""
    wholesale = (
        "Commerce de gros de tapis, couvertures et autres articles similaires "
        "à base de matières textiles"
    )
    assert classify_categories([wholesale]) is None
    assert classify_categories(["Tapis (fabrication)", wholesale]) == "carpet_weaving"


def test_classify_categories_drops_factory_only():
    """Production industrielle (not craft) → None even with a generic keyword."""
    factory = "Fabrication industrielle de vaisselle en poterie fine, en céramique ou en porcelaine"
    assert classify_categories([factory]) is None


# --- normalize_name --------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("AB ONE CERAM", "aboneceram"),
        ("Bijouterie Nada", "bijouterienada"),
        ("مجوهرات كاتشو", ""),  # non-Latin diacritics are stripped entirely
        ("  Oran   El Hamri  ", "oranelhamri"),
        ("", ""),
        ("Zoo-Métal, Arts", "zoometalarts"),
    ],
)
def test_normalize_name(name, expected):
    assert normalize_name(name) == expected


# --- transform (dedup vs OSM) ---------------------------------------------


def _pm_rec(pm_id=1, name="ATELIER CERAMIQUE", wilaya=16, cats=None):
    return {
        "pm_id": pm_id,
        "name": name,
        "slug": f"x-{pm_id}",
        "activity_description": "FABRICATION DE CERAMIQUE.",
        "categories": cats or ["Céramique (artisanat)"],
        "addresses": [
            {"street": "1 RUE X", "city": "Alger", "wilaya": "Alger", "wilaya_code": str(wilaya)}
        ],
        "phones": ["+213.771000000"],
        "emails": [],
        "websites": ["http://example.com"],
        "source": "pagesmaghreb",
        "source_url": f"https://www.pagesmaghreb.com/entreprise/x-{pm_id}/alger-16/algerie",
        "latitude": 36.7,
        "longitude": 3.0,
    }


def test_transform_dedupe_vs_osm():
    osm_keys = {(normalize_name("Atelier Bijoux Kabyles"), 16)}
    pm = [
        _pm_rec(1, "ATELIER BIJOUX KABYLES", 16),  # normalized match -> dropped
        _pm_rec(2, "ATELIER CERAMIQUE X", 16),  # keep
        _pm_rec(2, "ATELIER CERAMIQUE X", 16),  # duplicate pm_id -> skipped
    ]
    rows, dup, n_uniq = transform(pm, osm_keys)
    assert dup == 1
    assert n_uniq == 1  # pm_id 1 was dropped by the OSM dedup, pm_id 2 is unique
    assert len(rows) == 1
    assert rows[0]["craft_type"] == "pottery"
    assert rows[0]["wilaya_id"] == 16
    assert rows[0]["phone"] == "+213771000000"
    assert rows[0]["whatsapp"] == "+213771000000"
    assert rows[0]["metadata"]["source"] == "pagesmaghreb"
    assert rows[0]["metadata"]["pm_id"] == 2
    assert rows[0]["is_verified"] is True
    assert rows[0]["address"] == "1 RUE X, Alger"


def test_transform_phone_fixed_line_not_whatsapp():
    pm = [_pm_rec(3, "ABC", 16)]
    pm[0]["phones"] = ["+213.41111111"]  # landline, not mobile
    rows, _, _ = transform(pm, set())
    assert rows[0]["phone"] == "+21341111111"
    assert rows[0]["whatsapp"] is None


def test_transform_no_contact_fields_kept_with_address():
    """Directory-registered firm with only an address is still kept (verifiable)."""
    pm = [_pm_rec(4, "ABC", 16)]
    pm[0]["phones"] = []
    pm[0]["emails"] = []
    pm[0]["websites"] = []
    rows, _, _ = transform(pm, set())
    assert len(rows) == 1
    assert rows[0]["phone"] is None
    assert rows[0]["website"] is None
    assert rows[0]["address"] == "1 RUE X, Alger"


def test_transform_website_normalization():
    pm = [_pm_rec(5, "ABC", 16)]
    pm[0]["websites"] = ["www.example.com"]
    rows, _, _ = transform(pm, set())
    assert rows[0]["website"] == "https://www.example.com"
