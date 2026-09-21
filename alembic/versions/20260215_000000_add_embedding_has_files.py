"""Add embedding_has_files flag to tenders

Revision ID: 20260215_000000
Revises: 20260127_130000
Create Date: 2026-02-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260215_000000'
down_revision: Union[str, Sequence[str], None] = '20260127_130000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenders', sa.Column('embedding_has_files', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('tenders', 'embedding_has_files')
