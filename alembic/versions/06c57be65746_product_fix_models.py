"""product fix  models

Revision ID: 06c57be65746
Revises: d757a0b3ce21
Create Date: 2025-04-06 07:49:52.634125

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '06c57be65746'
down_revision: Union[str, None] = 'd757a0b3ce21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('products', 'image_urls')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('products', sa.Column('image_urls', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True))
    # ### end Alembic commands ###
