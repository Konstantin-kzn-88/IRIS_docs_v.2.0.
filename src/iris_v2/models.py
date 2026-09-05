from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    organization_name: Mapped[str] = mapped_column(Text, nullable=False)
    opo_name: Mapped[str] = mapped_column(Text, nullable=False)
    opo_registration_number: Mapped[str] = mapped_column(Text, nullable=False)
    organization_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    opo_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
