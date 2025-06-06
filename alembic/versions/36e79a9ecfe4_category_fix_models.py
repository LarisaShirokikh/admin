"""category fix models

Revision ID: 36e79a9ecfe4
Revises: a276f3f51e01
Create Date: 2025-04-07 17:16:05.216965

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36e79a9ecfe4'
down_revision: Union[str, None] = 'a276f3f51e01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('categories', sa.Column('image_url', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('categories', 'image_url')
    # ### end Alembic commands ###
