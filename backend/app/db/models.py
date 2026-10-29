"""
SQLAlchemy ORM models for all Novaliseo entities (Section 6).
Uses UUID PKs, created_at/updated_at, and JSON for flexible fields.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── Master data ───────────────────────────────────────────────────────────────

class PartMaster(Base):
    __tablename__ = "part_master"

    part_number: Mapped[str] = mapped_column(String, primary_key=True)
    part_name: Mapped[str] = mapped_column(String, nullable=False)
    drawing_rev: Mapped[str] = mapped_column(String, nullable=False)
    drawing_uri: Mapped[str] = mapped_column(String, nullable=False)  # DXF/PDF in storage
    material: Mapped[str | None] = mapped_column(String, nullable=True)
    process: Mapped[str | None] = mapped_column(String, nullable=True)
    tolerances: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    camera_recipe: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calibration: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ── Inspection job ─────────────────────────────────────────────────────────────

class InspectionJob(Base):
    __tablename__ = "inspection_job"

    job_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    part_number: Mapped[str | None] = mapped_column(String, ForeignKey("part_master.part_number"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="CREATED")
    current_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dimensional_status: Mapped[str | None] = mapped_column(String, nullable=True)  # PASS|FAIL
    defect_found: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    final_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    loop_counters: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    part: Mapped[PartMaster | None] = relationship("PartMaster", lazy="select")
    images: Mapped[list[ImageAsset]] = relationship("ImageAsset", back_populates="job", lazy="select")
    dimension_results: Mapped[list[DimensionResult]] = relationship("DimensionResult", back_populates="job", lazy="select")
    gate_decisions: Mapped[list[GateDecision]] = relationship("GateDecision", back_populates="job", lazy="select")
    defects: Mapped[list[Defect]] = relationship("Defect", back_populates="job", lazy="select")


# ── Assets ─────────────────────────────────────────────────────────────────────

class ImageAsset(Base):
    __tablename__ = "image_asset"

    image_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # raw|processed|mask|overlay
    uri: Mapped[str] = mapped_column(String, nullable=False)
    angle: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped[InspectionJob] = relationship("InspectionJob", back_populates="images")


# ── Dimensional results ────────────────────────────────────────────────────────

class DimensionResult(Base):
    __tablename__ = "dimension_result"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    feature_id: Mapped[str] = mapped_column(String, nullable=False)
    feature_type: Mapped[str] = mapped_column(String, nullable=False)  # hole|edge|contour
    nominal: Mapped[float] = mapped_column(Float, nullable=False)
    tol_plus: Mapped[float] = mapped_column(Float, nullable=False)
    tol_minus: Mapped[float] = mapped_column(Float, nullable=False)
    measured: Mapped[float] = mapped_column(Float, nullable=False)
    deviation: Mapped[float] = mapped_column(Float, nullable=False)
    within_tolerance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_uri: Mapped[str | None] = mapped_column(String, nullable=True)

    job: Mapped[InspectionJob] = relationship("InspectionJob", back_populates="dimension_results")


# ── Gate decisions ─────────────────────────────────────────────────────────────

class GateDecision(Base):
    __tablename__ = "gate_decision"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    gate: Mapped[str] = mapped_column(String, nullable=False)  # GATE1|LABEL|GATE2|GATE3
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[InspectionJob] = relationship("InspectionJob", back_populates="gate_decisions")


# ── Defects ────────────────────────────────────────────────────────────────────

class Defect(Base):
    __tablename__ = "defect"

    defect_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    image_id: Mapped[str | None] = mapped_column(String, ForeignKey("image_asset.image_id"), nullable=True)
    defect_type: Mapped[str] = mapped_column(String, nullable=False)  # dent|scratch|crack|deformation|other
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mask_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    size_mm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)  # minor|major|critical
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # yolo|sam|anomalib|human
    human_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    original_label: Mapped[str | None] = mapped_column(String, nullable=True)

    job: Mapped[InspectionJob] = relationship("InspectionJob", back_populates="defects")


# ── Root cause predictions ─────────────────────────────────────────────────────

class RootCausePrediction(Base):
    __tablename__ = "root_cause_prediction"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    cause: Mapped[str] = mapped_column(String, nullable=False)
    effect: Mapped[str] = mapped_column(String, nullable=False)
    precautions: Mapped[list] = mapped_column(JSON, default=list)
    confidence_raw: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_cal: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)


# ── Final RCA ──────────────────────────────────────────────────────────────────

class FinalRCA(Base):
    __tablename__ = "final_rca"

    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), primary_key=True)
    selected_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cause: Mapped[str] = mapped_column(String, nullable=False)
    effect: Mapped[str] = mapped_column(String, nullable=False)
    corrective_actions: Mapped[list] = mapped_column(JSON, default=list)
    preventive_actions: Mapped[list] = mapped_column(JSON, default=list)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Reports ────────────────────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "report"

    report_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="DRAFT")  # DRAFT|PENDING|APPROVED|REJECTED
    pdf_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    xlsx_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    docx_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signature_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Corrective actions ─────────────────────────────────────────────────────────

class CorrectiveAction(Base):
    __tablename__ = "corrective_action"

    action_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    due_date: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date string
    status: Mapped[str] = mapped_column(String, default="OPEN")  # OPEN|IN_PROGRESS|DONE|OVERDUE
    evidence_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    effective: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Knowledge base ─────────────────────────────────────────────────────────────

class KBDocument(Base):
    __tablename__ = "kb_document"

    doc_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_uri: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)  # rca|historical_case|process|material
    title: Mapped[str] = mapped_column(String, nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # for idempotency


class KBChunk(Base):
    __tablename__ = "kb_chunk"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    doc_id: Mapped[str] = mapped_column(String, ForeignKey("kb_document.doc_id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # vector stored as JSON (pgvector in prod)
    part: Mapped[str | None] = mapped_column(String, nullable=True)
    material: Mapped[str | None] = mapped_column(String, nullable=True)
    process: Mapped[str | None] = mapped_column(String, nullable=True)
    defect_type: Mapped[str | None] = mapped_column(String, nullable=True)
    cause: Mapped[str | None] = mapped_column(String, nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)


class KBEdge(Base):
    __tablename__ = "kb_edge"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    src: Mapped[str] = mapped_column(String, nullable=False)
    rel: Mapped[str] = mapped_column(String, nullable=False)  # defect→cause, cause→action, etc.
    dst: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source_chunk: Mapped[str | None] = mapped_column(String, ForeignKey("kb_chunk.chunk_id"), nullable=True)


# ── Learning ───────────────────────────────────────────────────────────────────

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String, ForeignKey("inspection_job.job_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # label|rca_choice|outcome
    ai_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    human_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    model: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, default="staging")  # staging|production|archived
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uri: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("model", "version", name="uq_model_version"),)


# ── Audit log (append-only) ────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    node: Mapped[str | None] = mapped_column(String, nullable=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    state_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Users ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "user"

    user_id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="operator")
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
