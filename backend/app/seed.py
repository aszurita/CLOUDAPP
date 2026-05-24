from app.db.session import SessionLocal
from app.services.seed import seed_demo_data


def main() -> None:
    with SessionLocal() as db:
        seed_demo_data(db)


if __name__ == "__main__":
    main()
