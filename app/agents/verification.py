"""ATHAR Data Quality Verification Agent — Pydantic AI for data verification.

Verifies POI data quality: descriptions, categories, coordinates, missing fields.
Gracefully degrades (logs dry-run) when no API key is configured.
"""

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


class VerificationResult(BaseModel):
    """Result of verifying a single POI."""

    poi_id: str = Field(..., description="UUID of the verified POI")
    description_ok: bool = Field(True, description="Is the description accurate/relevant?")
    description_suggestion: str | None = Field(None, description="Suggested description fix")
    category_ok: bool = Field(True, description="Does the category match the POI name?")
    category_suggestion: str | None = Field(None, description="Suggested category")
    missing_fields: list[str] = Field(default_factory=list, description="Important missing fields")
    issues: list[str] = Field(default_factory=list, description="All issues found")
    score: int = Field(5, ge=1, le=5, description="Overall data quality score (1-5)")


class BatchVerificationResult(BaseModel):
    """Result of batch verification."""

    total: int
    verified: int
    issues_found: int
    results: list[VerificationResult]


VERIFY_INSTRUCTIONS = (
    "You are an expert data quality auditor for Algeria's tourism database. "
    "Given a POI's name, category, description, OSM tags, and location, verify the data quality."

    "\n\nVERIFICATION CRITERIA:"
    "\n1. DESCRIPTION: Is the description accurate for the POI? Does it describe what this place actually is?"
    "\n2. CATEGORY: Is the category correct? A mosque→religious, a museum→museum, a beach→beach, etc."
    "\n3. COORDINATES: (Handled by separate geo-verification tool)"
    "\n4. MISSING FIELDS: What important information is missing? (phone, website, hours, photos)"

    "\n\nIMPORTANT:"
    "\n- If the description is auto-generated and generic (e.g., 'Tomb of saint — Type: religious'), flag it."
    "\n- If the description mentions a different location, flag it as inaccurate."
    "\n- If the category is clearly wrong, suggest the correct one."
    "\n- Be conservative: only flag clear issues."
    "\n- Score: 5=perfect, 4=minor issues, 3=needs work, 2=poor, 1=completely wrong."
)


@dataclass
class VerificationDeps:
    """Dependencies for the verification agent — currently minimal."""
    pass


def create_verification_agent(api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the POI data verification agent.

    Returns None if no API key is configured (graceful degradation).
    """
    if not api_key:
        logger.info("No OPENROUTER_API_KEY set — verification agent runs in dry-run mode")
        return None
    model = f"openrouter:{model_name}" if model_name else "openrouter:google/gemini-2.0-flash-lite"
    agent = Agent[VerificationDeps, VerificationResult](
        model=model,
        provider=OpenRouterProvider(api_key=api_key),
        output_type=VerificationResult,
        instructions=VERIFY_INSTRUCTIONS,
        model_settings={"temperature": 0.1, "max_tokens": 1024},
    )
    return agent


async def verify_poi_dry_run(
    poi_id: str,
    name: str,
    category: str,
    description: str | None,
    osm_tags: dict | None,
) -> VerificationResult:
    """Dry-run verification — rule-based checks without LLM."""
    issues: list[str] = []
    missing: list[str] = []

    description_ok = True
    description_suggestion = None
    category_ok = True
    category_suggestion = None
    score = 5

    # Check description quality
    if not description or len(description.strip()) < 30:
        issues.append("Description is too short or missing")
        description_ok = False
        score -= 1
    elif "—" in description and len(description) < 80:
        issues.append("Description appears to be auto-generated (contains '—' separator)")
        description_ok = False
        score -= 1

    # Check category
    if osm_tags:
        tag_category = _infer_category_from_tags(osm_tags)
        if tag_category and tag_category != category:
            issues.append(f"Category mismatch: OSM tags suggest '{tag_category}', current is '{category}'")
            category_ok = False
            category_suggestion = tag_category
            score -= 1

    # Check missing fields
    if osm_tags:
        if not osm_tags.get("phone") and not osm_tags.get("contact:phone"):
            missing.append("phone")
        if not osm_tags.get("website") and not osm_tags.get("contact:website"):
            missing.append("website")
        if not osm_tags.get("opening_hours"):
            missing.append("opening_hours")

    if missing:
        issues.append(f"Missing contact info: {', '.join(missing[:3])}")
        if score > 2:
            score -= 1

    return VerificationResult(
        poi_id=poi_id,
        description_ok=description_ok,
        description_suggestion=description_suggestion,
        category_ok=category_ok,
        category_suggestion=category_suggestion,
        missing_fields=missing[:5],
        issues=issues[:5],
        score=max(1, score),
    )


def _infer_category_from_tags(tags: dict) -> str | None:
    """Simple OSM tag → category mapping for verification."""
    tag_mapping = {
        "amenity": {"place_of_worship": "religious", "museum": "museum", "restaurant": "restaurant", "cafe": "cafe", "marketplace": "market", "theatre": "cultural", "cinema": "cultural", "library": "cultural"},
        "historic": {"*": "historical"},
        "leisure": {"park": "park", "beach_resort": "beach", "garden": "park", "nature_reserve": "natural"},
        "natural": {"*": "natural"},
        "tourism": {"museum": "museum", "artwork": "cultural", "gallery": "cultural", "viewpoint": "natural"},
        "building": {"museum": "museum"},
    }

    for tag_key, mapping in tag_mapping.items():
        val = tags.get(tag_key)
        if val:
            if val in mapping:
                return mapping[val]
            if "*" in mapping:
                return mapping["*"]
    return None
