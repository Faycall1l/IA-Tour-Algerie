"""Content-based recommendation engine with interaction signal extraction."""

import logging
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionItem
from app.models.experience import Experience
from app.models.favorite import Favorite
from app.models.poi import POI
from app.models.recommendation import Recommendation, UserPreference
from app.models.stay import Stay
from app.models.trip import Trip, TripItem

logger = logging.getLogger(__name__)

MODEL_VERSION = "cbf_v1"
INTERACTION_WEIGHTS = {"favorite": 3.0, "trip_item": 2.0, "collection": 2.5}


class RecommendationEngine:
    async def get_or_create_preferences(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> UserPreference:
        result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
        pref = result.scalar_one_or_none()
        if not pref:
            pref = UserPreference(id=uuid.uuid4(), user_id=user_id)
            db.add(pref)
            await db.flush()
        return pref

    async def extract_interaction_scores(self, db: AsyncSession, user_id: uuid.UUID) -> dict:
        cat_scores: dict[str, float] = defaultdict(float)
        wilaya_scores: dict[int, float] = defaultdict(float)
        tag_scores: dict[str, float] = defaultdict(float)
        durations: list[int] = []

        # Favorites (POI only for signal extraction)
        favs = await db.execute(
            select(Favorite).where(Favorite.user_id == user_id, Favorite.entity_type == "poi")
        )
        fav_list = favs.scalars().all()

        # Trip items via explicit user trip subquery
        user_trips = await db.execute(select(Trip.id).where(Trip.user_id == user_id))
        trip_ids = [r[0] for r in user_trips.all()]
        trip_items = []
        if trip_ids:
            ti_result = await db.execute(
                select(TripItem).where(
                    TripItem.trip_id.in_(trip_ids),
                    TripItem.item_type.in_(["poi", "experience", "stay"]),
                )
            )
            trip_items = ti_result.scalars().all()

        # Collection items via explicit user collection subquery
        user_cols = await db.execute(select(Collection.id).where(Collection.user_id == user_id))
        col_ids = [r[0] for r in user_cols.all()]
        col_items = []
        if col_ids:
            ci_result = await db.execute(
                select(CollectionItem).where(
                    CollectionItem.collection_id.in_(col_ids),
                    CollectionItem.entity_type.in_(["poi", "experience", "stay"]),
                )
            )
            col_items = ci_result.scalars().all()

        total = len(fav_list) + len(trip_items) + len(col_items)

        # Collect all interacted entity IDs for signal resolution
        all_entity_ids = set()
        for item in fav_list:
            all_entity_ids.add(item.entity_id)
        for item in trip_items:
            all_entity_ids.add(item.entity_id)
        for item in col_items:
            all_entity_ids.add(item.entity_id)

        if all_entity_ids:
            # POI signals
            poi_result = await db.execute(select(POI).where(POI.id.in_(all_entity_ids)))
            for poi in poi_result.scalars().all():
                cat_scores[poi.category] += 1.0
                wilaya_scores[poi.wilaya_id] += 1.0
                if poi.subtype:
                    tag_scores[poi.subtype] += 0.5
                if poi.suggested_duration_min:
                    durations.append(poi.suggested_duration_min)

            # Experience signals
            exp_result = await db.execute(
                select(Experience).where(Experience.id.in_(all_entity_ids))
            )
            for exp in exp_result.scalars().all():
                cat_scores[exp.category] += 1.0
                wilaya_scores[exp.wilaya_id] += 1.0

            # Stay signals
            stay_result = await db.execute(select(Stay).where(Stay.id.in_(all_entity_ids)))
            for stay in stay_result.scalars().all():
                cat_scores[stay.property_type] += 1.0
                wilaya_scores[stay.wilaya_id] += 1.0

        return {
            "category_scores": dict(cat_scores),
            "wilaya_scores": dict(wilaya_scores),
            "tag_scores": dict(tag_scores),
            "total_interactions": total,
            "favorite_count": len(fav_list),
            "trip_count": len(trip_items),
            "collection_count": len(col_items),
            "avg_duration_min": int(sum(durations) / len(durations)) if durations else None,
        }

    async def update_preferences_from_interactions(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> UserPreference:
        pref = await self.get_or_create_preferences(db, user_id)
        scores = await self.extract_interaction_scores(db, user_id)
        pref.interaction_score = scores

        # Auto-derive top categories if not explicitly set
        if not pref.preferred_categories and scores["category_scores"]:
            ranked = sorted(
                [(k, v) for k, v in scores["category_scores"].items()],
                key=lambda x: x[1],
                reverse=True,
            )
            pref.preferred_categories = [cat for cat, _ in ranked[:5]]

        if not pref.preferred_wilayas and scores["wilaya_scores"]:
            ranked_w = sorted(scores["wilaya_scores"].items(), key=lambda x: x[1], reverse=True)
            pref.preferred_wilayas = [w for w, _ in ranked_w[:5]]

        await db.flush()
        return pref

    def _score_candidate(
        self,
        candidate,
        entity_type: str,
        pref: UserPreference,
    ) -> tuple[float, str, str]:
        score = 0.0
        reasons = []

        # --- Category/type match ---
        if entity_type == "poi" or entity_type == "experience":
            entity_category = getattr(candidate, "category", None)
        elif entity_type == "stay":
            entity_category = getattr(candidate, "property_type", None)
        else:
            entity_category = None

        if (
            entity_category
            and pref.preferred_categories
            and entity_category in pref.preferred_categories
        ):
            idx = pref.preferred_categories.index(entity_category)
            score += 3.0 - idx * 0.5
            reasons.append(f"matches your interest in {entity_category}")

        if (
            entity_category
            and pref.avoided_categories
            and entity_category in pref.avoided_categories
        ):
            score -= 5.0
            reasons.append(f"avoids {entity_category} per your preference")

        # --- Wilaya match ---
        wilaya_id = getattr(candidate, "wilaya_id", None)
        if wilaya_id and pref.preferred_wilayas and wilaya_id in pref.preferred_wilayas:
            score += 2.0
            reasons.append(f"in wilaya {wilaya_id}")

        # --- Interaction score boost ---
        if pref.interaction_score:
            if entity_category:
                cat_boost = pref.interaction_score.get("category_scores", {}).get(
                    entity_category, 0
                )
                score += min(cat_boost * 0.3, 3.0)
            if wilaya_id:
                wil_boost = pref.interaction_score.get("wilaya_scores", {}).get(str(wilaya_id), 0)
                score += min(wil_boost * 0.2, 2.0)

        # --- Featured boost ---
        if getattr(candidate, "is_featured", False):
            score += 1.5
            reasons.append("featured attraction")

        # --- Has photo ---
        photos = (
            getattr(candidate, "photos", None)
            or getattr(candidate, "photo_url", None)
            or getattr(candidate, "photo_urls", None)
        )
        if photos:
            score += 0.5

        # --- Has fun fact ---
        if getattr(candidate, "fun_fact", None):
            score += 0.3

        explanation = "; ".join(reasons) if reasons else "general recommendation"
        reason_code = reasons[0].split()[0] if reasons else "general"

        return round(score, 2), explanation, reason_code

    async def generate_recommendations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        wilaya_id: int | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[Recommendation]:
        pref = await self.update_preferences_from_interactions(db, user_id)

        candidates = []
        types_to_query = [entity_type] if entity_type else ["poi", "experience", "stay"]

        for etype in types_to_query:
            if etype == "poi":
                q = select(POI).where(POI.latitude.isnot(None))
                if wilaya_id:
                    q = q.where(POI.wilaya_id == wilaya_id)
                q = q.order_by(POI.is_featured.desc(), func.random()).limit(200)
                result = await db.execute(q)
                for poi in result.scalars().all():
                    candidates.append((etype, poi))
            elif etype == "experience":
                q = select(Experience).where(Experience.status == "active")
                if wilaya_id:
                    q = q.where(Experience.wilaya_id == wilaya_id)
                q = q.order_by(func.random()).limit(100)
                result = await db.execute(q)
                for exp in result.scalars().all():
                    candidates.append((etype, exp))
            elif etype == "stay":
                q = select(Stay).where(Stay.is_active.is_(True))
                if wilaya_id:
                    q = q.where(Stay.wilaya_id == wilaya_id)
                q = q.order_by(func.random()).limit(100)
                result = await db.execute(q)
                for stay in result.scalars().all():
                    candidates.append((etype, stay))

        scored = []
        for etype, candidate in candidates:
            s, explanation, reason = self._score_candidate(candidate, etype, pref)
            scored.append((s, explanation, reason, etype, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        # Delete old unpersisted recs for this user (same model version)
        old = await db.execute(
            select(Recommendation).where(
                Recommendation.user_id == user_id,
                Recommendation.model_version == MODEL_VERSION,
                Recommendation.is_seen.is_(False),
                Recommendation.is_dismissed.is_(False),
            )
        )
        for old_rec in old.scalars().all():
            await db.delete(old_rec)

        recs = []
        for s, explanation, reason_code, etype, candidate in top:
            rec = Recommendation(
                id=uuid.uuid4(),
                user_id=user_id,
                entity_type=etype,
                entity_id=candidate.id,
                wilaya_id=getattr(candidate, "wilaya_id", None),
                score=s,
                explanation=explanation,
                reason_code=reason_code,
                model_version=MODEL_VERSION,
            )
            db.add(rec)
            recs.append(rec)

        await db.flush()
        return recs


recommendation_engine = RecommendationEngine()
