"""categorie image

Revision ID: 24462822979b
Revises: c1cdd5e0bcf9
Create Date: 2025-04-27 10:27:47.192633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24462822979b'
down_revision: Union[str, None] = 'c1cdd5e0bcf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('catalogs', sa.Column('image', sa.String(length=255), nullable=True))
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
    op.drop_column('catalogs', 'image')
    # ### end Alembic commands ###
