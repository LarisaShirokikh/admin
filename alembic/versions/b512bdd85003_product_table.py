"""product table

Revision ID: b512bdd85003
Revises: d323665dbece
Create Date: 2025-04-26 08:43:12.849577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b512bdd85003'
down_revision: Union[str, None] = 'd323665dbece'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('catalogs', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('categories', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('categories', 'brand_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('products', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('products', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('categories', 'brand_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('categories', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    op.alter_column('catalogs', 'slug',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    # ### end Alembic commands ###
