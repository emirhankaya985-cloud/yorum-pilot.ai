"""Telegram secure linking and dedupe tables.

Revision ID: 0002_telegram
Revises: 0001_initial
"""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision = '0002_telegram'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    op.drop_table('telegram_updates')
    op.drop_table('telegram_bindings')
    op.drop_table('telegram_pairings')
