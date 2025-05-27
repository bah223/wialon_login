"""update token tables

Revision ID: 2025_04_19_01
Revises: ed077937a534
Create Date: 2025-04-19 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = '2025_04_19_01'
down_revision: Union[str, None] = 'ed077937a534'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Эта миграция больше не нужна, так как колонка linked_data
    # уже создается в первой миграции
    pass


def downgrade() -> None:
    # Также убираем downgrade, так как колонка создается в первой миграции
    pass 