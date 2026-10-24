"""Called on a schedule by Render cron or external scheduler."""
from .db import SessionLocal
from .lifecycle import purge_expired


def main():
    with SessionLocal() as db:
        print(f'Expired review caches removed: {purge_expired(db)}')


if __name__ == '__main__':
    main()
