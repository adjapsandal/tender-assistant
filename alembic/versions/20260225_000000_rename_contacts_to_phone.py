"""Rename contacts to phone in companies table

Revision ID: 20260225_000000
Revises: 20260223_000000
Create Date: 2026-02-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '20260225_000000'
down_revision: Union[str, Sequence[str], None] = '20260223_000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('companies', 'contacts', new_column_name='phone')


def downgrade() -> None:
    op.alter_column('companies', 'phone', new_column_name='contacts')
