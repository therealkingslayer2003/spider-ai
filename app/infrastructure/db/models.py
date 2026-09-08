from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AssetTypeModel(Base):
    __tablename__ = "asset_type"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    assets: Mapped[list["AssetModel"]] = relationship(back_populates="asset_type")


class AssetModel(Base):
    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("asset_type_id", "name", name="uq_asset_type_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_type_id: Mapped[int] = mapped_column(
        ForeignKey("asset_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    asset_type: Mapped[AssetTypeModel] = relationship(back_populates="assets")
    research_artifacts: Mapped[list["ResearchArtifactModel"]] = relationship(
        back_populates="asset"
    )
    evidence_bundles: Mapped[list["EvidenceModel"]] = relationship(
        back_populates="asset"
    )


class ResearchArtifactModel(Base):
    __tablename__ = "research_artifact"
    __table_args__ = (
        Index(
            "ix_research_artifact_asset_created_at",
            "asset_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("asset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    data_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)

    asset: Mapped[AssetModel] = relationship(back_populates="research_artifacts")
    snapshot: Mapped["SnapshotResearchArtifactModel | None"] = relationship(
        back_populates="research_artifact",
        uselist=False,
    )


class EvidenceModel(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_asset_created_at", "asset_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("asset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    context_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    asset: Mapped[AssetModel] = relationship(back_populates="evidence_bundles")
    snapshot: Mapped["SnapshotResearchArtifactModel | None"] = relationship(
        back_populates="evidence",
        uselist=False,
    )


class SnapshotResearchArtifactModel(Base):
    __tablename__ = "snapshot_research_artifact"

    research_artifact_id: Mapped[int] = mapped_column(
        ForeignKey("research_artifact.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    output_json: Mapped[str] = mapped_column(Text, nullable=False)

    research_artifact: Mapped[ResearchArtifactModel] = relationship(
        back_populates="snapshot"
    )
    evidence: Mapped[EvidenceModel] = relationship(back_populates="snapshot")
