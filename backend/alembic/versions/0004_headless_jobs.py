"""Additive persisted cron ledger, OAuth denial guard, and Telegram receipts."""
from alembic import op
from sqlalchemy import select, func
from app.db import Base
from app import models  # noqa: F401

revision = "0004_headless_jobs"
down_revision = "0003_google_oauth"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ("autonomous_runs", "autonomous_sync_blocks", "autonomous_digests"):
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    names = ("autonomous_digests", "autonomous_sync_blocks", "autonomous_runs")
    for name in names:
        table = Base.metadata.tables[name]
        if table.exists(bind) and bind.execute(select(func.count()).select_from(table)).scalar_one():
            raise RuntimeError("Refuse to delete durable automation history")
    for name in names:
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
