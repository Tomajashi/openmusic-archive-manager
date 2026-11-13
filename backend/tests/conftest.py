from pathlib import Path
from typing import Generator
import pytest
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.services.search_engine import search_cache


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path) -> Generator[Path, None, None]:
    dl_dir = tmp_path / "downloads"
    music_dir = tmp_path / "music"
    dl_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)

    settings.download_dir = str(dl_dir)
    settings.music_dir = str(music_dir)
    search_cache.clear()

    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield tmp_path
    engine.dispose()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
