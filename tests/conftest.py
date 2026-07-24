import asyncio
import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import TransportOperator  # noqa: F401 — ensure table is created
from app.models.poi import POI
from app.models.user import User
from app.models.wilaya import Wilaya
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TEST_DB_URL = settings.database.url.replace("athar_db", "athar_test")

test_engine = create_async_engine(TEST_DB_URL, echo=False)
test_async_session = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed base data needed by all tests (wilayas)
    async with test_async_session() as session:
        from app.models.wilaya import Wilaya
        wilayas = [
            (1, "أدرار", "Adrar", "Adrar"),
            (2, "الشلف", "Chlef", "Chlef"),
            (3, "الأغواط", "Laghouat", "Laghouat"),
            (4, "أم البواقي", "Oum El Bouaghi", "Oum El Bouaghi"),
            (5, "باتنة", "Batna", "Batna"),
            (6, "بجاية", "Bejaia", "Béjaïa"),
            (7, "بسكرة", "Biskra", "Biskra"),
            (8, "بشار", "Bechar", "Béchar"),
            (9, "البليدة", "Blida", "Blida"),
            (10, "البويرة", "Bouira", "Bouira"),
            (11, "تمنراست", "Tamanrasset", "Tamanrasset"),
            (12, "تبسة", "Tebessa", "Tébessa"),
            (13, "تلمسان", "Tlemcen", "Tlemcen"),
            (14, "تيارت", "Tiaret", "Tiaret"),
            (15, "تيزي وزو", "Tizi Ouzou", "Tizi Ouzou"),
            (16, "الجزائر", "Algiers", "Alger"),
            (17, "الجلفة", "Djelfa", "Djelfa"),
            (18, "جيجل", "Jijel", "Jijel"),
            (19, "سطيف", "Setif", "Sétif"),
            (20, "سعيدة", "Saida", "Saïda"),
            (21, "سكيكدة", "Skikda", "Skikda"),
            (22, "سيدي بلعباس", "Sidi Bel Abbes", "Sidi Bel Abbès"),
            (23, "عنابة", "Annaba", "Annaba"),
            (24, "قالمة", "Guelma", "Guelma"),
            (25, "قسنطينة", "Constantine", "Constantine"),
            (26, "المدية", "Medea", "Médéa"),
            (27, "مستغانم", "Mostaganem", "Mostaganem"),
            (28, "المسيلة", "M'Sila", "M'Sila"),
            (29, "معسكر", "Mascara", "Mascara"),
            (30, "ورقلة", "Ouargla", "Ouargla"),
            (31, "وهران", "Oran", "Oran"),
            (32, "البيض", "El Bayadh", "El Bayadh"),
            (33, "إليزي", "Illizi", "Illizi"),
            (34, "برج بوعريريج", "Bordj Bou Arreridj", "Bordj Bou Arreridj"),
            (35, "بومرداس", "Boumerdes", "Boumerdès"),
            (36, "الطارف", "El Tarf", "El Tarf"),
            (37, "تندوف", "Tindouf", "Tindouf"),
            (38, "تيسمسيلت", "Tissemsilt", "Tissemsilt"),
            (39, "الوادي", "El Oued", "El Oued"),
            (40, "خنشلة", "Khenchela", "Khenchela"),
            (41, "سوق أهراس", "Souk Ahras", "Souk Ahras"),
            (42, "تيبازة", "Tipaza", "Tipaza"),
            (43, "ميلة", "Mila", "Mila"),
            (44, "عين الدفلى", "Ain Defla", "Aïn Defla"),
            (45, "النعامة", "Naama", "Naâma"),
            (46, "عين تموشنت", "Ain Temouchent", "Aïn Témouchent"),
            (47, "غرداية", "Ghardaia", "Ghardaïa"),
            (48, "غليزان", "Relizane", "Relizane"),
            (49, "تيميمون", "Timimoun", "Timimoun"),
            (50, "بني عباس", "Beni Abbes", "Béni Abbès"),
            (51, "أين صالح", "Ain Salah", "Aïn Salah"),
            (52, "أين قزام", "Ain Guezzam", "Aïn Guezzam"),
            (53, "تقرت", "Touggourt", "Touggourt"),
            (54, "جانت", "Djanet", "Djanet"),
            (55, "المغير", "El M'Ghair", "El M'Ghair"),
            (56, "المنيعة", "El Meniaa", "El Meniaa"),
            (57, "أولاد جلال", "Ouled Djellal", "Ouled Djellal"),
            (58, "برج باجي مختار", "Bordj Badji Mokhtar", "Bordj Badji Mokhtar"),
        ]
        for wid, ar, en, fr in wilayas:
            existing = await session.get(Wilaya, wid)
            if not existing:
                session.add(Wilaya(id=wid, name_ar=ar, name_en=en, name_fr=fr, latitude=36.0, longitude=3.0))
        await session.commit()
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncIterator[AsyncSession]:
    async with test_async_session() as session:
        yield session


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with test_async_session() as session:
        yield session


class _MockTwilio:
    is_available = False
    sms_available = False
    whatsapp_available = False

    async def send_otp(self, phone: str) -> dict | None:
        return None

    async def verify_otp(self, phone: str, code: str) -> bool:
        return False

    async def send_whatsapp(self, to_phone: str, message: str) -> bool:
        return False


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = override_get_db
    app.state.skip_rate_limit = True

    from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer

    storage_mock = AsyncMock()
    storage_mock.upload = AsyncMock(return_value="https://minio.test/uploads/photo.jpg")
    app.state.storage = storage_mock
    app.state.embedder = AsyncMock()
    app.state.vector_search = AsyncMock()
    app.state.trip_optimizer = TripOptimizer()
    app.state.trip_brief_generator = TripBriefGenerator()
    app.state.transit_routing = AsyncMock()
    app.state.twilio = _MockTwilio()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), phone="+213555123456")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), phone="+213555000000", role="admin")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_token(test_user: User) -> str:
    return create_access_token(str(test_user.id), test_user.role)


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    return create_access_token(str(admin_user.id), admin_user.role)


@pytest_asyncio.fixture
async def auth_headers(user_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def sample_poi(db: AsyncSession) -> POI:
    existing = await db.get(Wilaya, 1)
    if not existing:
        wilaya = Wilaya(
            id=1,
            name_ar="أدرار",
            name_en="Adrar",
            name_fr="Adrar",
            latitude=27.873,
            longitude=-0.295,
        )
        db.add(wilaya)
        await db.commit()

    poi = POI(
        name="Grande Mosquée d'Alger",
        category="religious",
        wilaya_id=1,
        latitude=36.737,
        longitude=3.068,
        description="Iconic mosque on the bay of Algiers",
        entry_fee_dzd=0,
    )
    db.add(poi)
    await db.commit()
    await db.refresh(poi)
    return poi
