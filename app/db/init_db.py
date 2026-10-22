from app.db.base import Base
from app.db.seed import seed_database
from app.db.session import SessionLocal, engine


def init_database(seed: bool = True) -> None:
    Base.metadata.create_all(bind=engine)
    if seed:
        with SessionLocal() as db:
            seed_database(db)
