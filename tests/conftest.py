import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
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


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = override_get_db

    from app.services.trip_optimizer import TripBriefGenerator, TripOptimizer
    from app.services.twilio import TwilioService

    app.state.storage = None
    app.state.embedder = None
    app.state.vector_search = None
    app.state.trip_optimizer = TripOptimizer()
    app.state.trip_brief_generator = TripBriefGenerator()
    app.state.twilio = TwilioService()

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
