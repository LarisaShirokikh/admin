"""categorie image

Revision ID: e8db9a2649e0
Revises: 24462822979b
Create Date: 2025-04-27 10:41:24.972045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8db9a2649e0'
down_revision: Union[str, None] = '24462822979b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('catalog_images',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('catalog_id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('is_main', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['catalog_id'], ['catalogs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_images_id'), 'catalog_images', ['id'], unique=False)
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
    op.drop_index(op.f('ix_catalog_images_id'), table_name='catalog_images')
    op.drop_table('catalog_images')
    # ### end Alembic commands ###
