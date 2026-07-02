ATHAR_PRICES_PAYLOAD = {
    "route": {"type": "keyword"},
    "mode": {"type": "keyword"},
    "price_min_dzd": {"type": "float"},
    "price_max_dzd": {"type": "float"},
    "station": {"type": "keyword"},
    "wilaya": {"type": "keyword"},
    "verified_at": {"type": "date"},
}

ATHAR_SITES_PAYLOAD = {
    "name": {"type": "keyword"},
    "wilaya": {"type": "keyword"},
    "category": {"type": "keyword"},
    "description": {"type": "text"},
    "entry_fee_dzd": {"type": "float"},
}
