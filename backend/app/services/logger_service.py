import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models import SystemLog

logger = logging.getLogger("openmusic")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_event(
    level: str,
    category: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> None:
    lvl = level.upper()
    if lvl == "ERROR":
        logger.error("[%s] %s", category, message)
    elif lvl == "WARNING":
        logger.warning("[%s] %s", category, message)
    else:
        logger.info("[%s] %s", category, message)

    own_session = False
    session = db
    try:
        if session is None:
            session = SessionLocal()
            own_session = True
        entry = SystemLog(
            level=lvl,
            category=category.upper(),
            message=message,
            details=details or {},
        )
        session.add(entry)
        session.commit()
    except Exception:
        if session and own_session:
            session.rollback()
    finally:
        if session and own_session:
            session.close()
