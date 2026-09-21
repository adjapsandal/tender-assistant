"""Refactor database: simplify SKU structure

Revision ID: 20260127_130000
Revises: 20260127_120000
Create Date: 2026-01-27 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260127_130000'
down_revision: Union[str, Sequence[str], None] = '20260127_120000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Удаляем старые таблицы
    op.drop_table('tender_history')
    op.drop_table('inclusion_filters')
    op.drop_table('exclusion_filters')
    op.drop_table('skus')  # Старая таблица с overengineering

    # 2. Переименовываем search_presets → skus
    op.rename_table('search_presets', 'skus')

    # 3. Обновляем колонки в новой skus
    # Убираем sort_order (не нужен), добавляем description
    op.add_column('skus', sa.Column('description', sa.Text(), nullable=True))
    op.drop_column('skus', 'sort_order')


def downgrade() -> None:
    """Downgrade schema."""
    # Восстанавливаем search_presets
    op.rename_table('skus', 'search_presets')

    op.add_column('search_presets', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
    op.drop_column('search_presets', 'description')

    # Восстанавливаем старые таблицы
    op.create_table('skus',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category', sa.String(100), nullable=True),
    sa.Column('synonyms', sa.JSON(), nullable=True),
    sa.Column('characteristics', sa.JSON(), nullable=True),
    sa.Column('has_ru', sa.Boolean(), nullable=False),
    sa.Column('has_ss', sa.Boolean(), nullable=False),
    sa.Column('has_gisp', sa.Boolean(), nullable=False),
    sa.Column('shelf_life_months', sa.Integer(), nullable=True),
    sa.Column('price_min', sa.Float(), nullable=True),
    sa.Column('price_max', sa.Float(), nullable=True),
    sa.Column('embedding', sa.Float(), nullable=True),  # будет pgvector
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], )
    )
    op.create_index('ix_skus_company_id', 'skus', ['company_id'], unique=False)
    op.create_index('ix_skus_category', 'skus', ['category'], unique=False)
    op.create_index('ix_skus_is_active', 'skus', ['is_active'], unique=False)

    op.create_table('exclusion_filters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('word', sa.String(100), nullable=False),
    sa.Column('category', sa.String(50), nullable=True),
    sa.Column('context_rule', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], )
    )
    op.create_index('ix_exclusion_filters_company_id', 'exclusion_filters', ['company_id'], unique=False)

    op.create_table('inclusion_filters',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('word', sa.String(100), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], )
    )
    op.create_index('ix_inclusion_filters_company_id', 'inclusion_filters', ['company_id'], unique=False)

    op.create_table('tender_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('result', sa.String(50), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('participated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], )
    )
    op.create_index('ix_tender_history_tender_id', 'tender_history', ['tender_id'], unique=False)
