from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class Topic(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "topics"

    slug: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    icon: Mapped[str | None]
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
