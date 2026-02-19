"""CRUD operations for Evening Draft users (eveningdraft schema)."""

import uuid

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.eveningdraft.models import EveningDraftUser, EDUserCreate


DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def create_user(*, session: Session, user_create: EDUserCreate) -> EveningDraftUser:
    db_obj = EveningDraftUser.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def get_user_by_email(*, session: Session, email: str) -> EveningDraftUser | None:
    statement = select(EveningDraftUser).where(EveningDraftUser.email == email)
    return session.exec(statement).first()


def authenticate(*, session: Session, email: str, password: str) -> EveningDraftUser | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
