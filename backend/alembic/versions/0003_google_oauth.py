"""Owner-only Google OAuth state and encrypted refresh grant (additive).

Revision ID: 0003_google_oauth
Revises: 0002_telegram
"""
from alembic import op
from sqlalchemy import select, func
from app.db import Base
from app import models  # noqa: F401

revision = "0003_google_oauth"
down_revision = "0002_telegram"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ("google_oauth_attempts", "google_connections"):
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in ("google_oauth_attempts", "google_connections"):
        table = Base.metadata.tables[name]
        if table.exists(bind):
            if bind.execute(select(func.count()).select_from(table)).scalar_one() != 0:
                raise RuntimeError("Refuse downgrade: existing owner OAuth grants must not be deleted")
    for name in ("google_connections", "google_oauth_attempts"):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
