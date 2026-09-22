from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class Team(UUIDPrimaryKey, Timestamps, Base):
    """Which part of the organisation owns a video: Payments, Fraud, Core Banking, …

    Topics say what a video is about; a team says who it came from. The two filters are
    independent, so "Fraud" and "BigQuery" can be combined.
    """

    __tablename__ = "teams"

    slug: Mapped[str]
    name: Mapped[str]
    description: Mapped[str | None]
    division: Mapped[str | None]
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
