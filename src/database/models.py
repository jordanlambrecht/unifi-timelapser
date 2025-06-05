#!/usr/bin/env python3
# src/database/models.py
"""
SQLAlchemy database models
"""

import uuid


from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    Date,
    Float,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    TIMESTAMP,
    text,
    event,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func

Base = declarative_base()


class Camera(Base):
    """Camera configuration and status table"""

    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    url_hash = Column(String(64), unique=True, nullable=False)
    encryption_key_ref = Column(String(64), nullable=True)
    last_health_check = Column(TIMESTAMP(timezone=True), nullable=True)
    connection_failures = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    rotation = Column(String(20), default="none", nullable=False)
    day_counter_enabled = Column(Boolean, default=False, nullable=False)
    day_counter_start_date = Column(Date, nullable=True)
    camera_metadata = Column(JSONB, default={}, nullable=False)
    day_overlay_position = Column(String(20), default="top-right", nullable=False)
    day_overlay_style = Column(
        JSONB,
        default={
            "font_size": 24,
            "font_color": "#FFFFFF",
            "background_color": "#000000",
            "background_opacity": 0.7,
            "font_family": "Arial",
        },
        nullable=False,
    )
    created_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    images = relationship(
        "Image", back_populates="camera", cascade="all, delete-orphan"
    )
    timelapse_batches = relationship(
        "TimelapseBatch", back_populates="camera", cascade="all, delete-orphan"
    )
    capture_attempts = relationship(
        "CaptureAttempt", back_populates="camera", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "rotation IN ('none', 'left', 'right', 'invert')", name="check_rotation"
        ),
        CheckConstraint(
            "day_overlay_position IN ('top-left', 'top-right', 'bottom-left', 'bottom-right')",
            name="check_overlay_position",
        ),
        Index("idx_cameras_name", "name"),
        Index("idx_cameras_enabled", "enabled"),
        Index("idx_cameras_overlay_gin", "day_overlay_style", postgresql_using="gin"),
    )

    @validates("rotation")
    def validate_rotation(self, key, rotation):
        valid_rotations = ["none", "left", "right", "invert"]
        if rotation not in valid_rotations:
            raise ValueError(
                f"Invalid rotation: {rotation}. Must be one of {valid_rotations}"
            )
        return rotation

    def __repr__(self):
        return f"<Camera(id={self.id}, name='{self.name}', enabled={self.enabled})>"


class Image(Base):
    """Captured images table"""

    __tablename__ = "images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    camera_id = Column(
        Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    format = Column(String(10), nullable=False)
    quality_score = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True)
    captured_at = Column(TIMESTAMP(timezone=True), nullable=False)
    day_number = Column(Integer, nullable=True)
    processing_metadata = Column(JSONB, default={}, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    camera = relationship("Camera", back_populates="images")
    timelapse_images = relationship(
        "TimelapseImage", back_populates="image", cascade="all, delete-orphan"
    )
    capture_attempt = relationship(
        "CaptureAttempt", back_populates="image", uselist=False
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("quality_score BETWEEN 0 AND 100", name="check_quality_score"),
        CheckConstraint("file_size_bytes > 0", name="check_file_size_positive"),
        Index(
            "idx_images_camera_captured_desc",
            "camera_id",
            "captured_at",
            postgresql_using="btree",
        ),
        Index("idx_images_captured_at_brin", "captured_at", postgresql_using="brin"),
        Index("idx_images_metadata_gin", "processing_metadata", postgresql_using="gin"),
        Index("idx_images_camera_day", "camera_id", "day_number"),
        Index("idx_images_captured_at", "captured_at"),
    )

    def __repr__(self):
        return f"<Image(id={self.id}, camera_id={self.camera_id}, filename='{self.filename}')>"


class TimelapseBatch(Base):
    """Timelapse batch tracking table"""

    __tablename__ = "timelapse_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(
        Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    batch_type = Column(String(20), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    output_filename = Column(String(255), nullable=True)
    output_path = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    frame_rate = Column(Integer, default=30, nullable=False)
    total_frames = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    generation_mode = Column(String(20), nullable=False)
    day_overlay_applied = Column(Boolean, default=False, nullable=False)
    day_range_start = Column(Integer, nullable=True)
    day_range_end = Column(Integer, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    camera = relationship("Camera", back_populates="timelapse_batches")
    timelapse_images = relationship(
        "TimelapseImage", back_populates="timelapse_batch", cascade="all, delete-orphan"
    )
    share_batches = relationship(
        "ShareBatch", back_populates="timelapse_batch", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "batch_type IN ('continuous', 'checkpoint', 'manual')",
            name="check_batch_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="check_status",
        ),
        CheckConstraint(
            "generation_mode IN ('every_capture', 'periodic', 'manual_only')",
            name="check_generation_mode",
        ),
        CheckConstraint("frame_rate > 0", name="check_frame_rate_positive"),
        CheckConstraint("total_frames >= 0", name="check_total_frames_non_negative"),
        Index(
            "idx_batches_pending",
            "status",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("idx_batches_camera_status", "camera_id", "status"),
        Index("idx_batches_type_status", "batch_type", "status"),
    )

    def __repr__(self):
        return f"<TimelapseBatch(id={self.id}, camera_id={self.camera_id}, status='{self.status}')>"


class TimelapseImage(Base):
    """Junction table linking images to timelapse batches"""

    __tablename__ = "timelapse_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timelapse_batch_id = Column(
        Integer, ForeignKey("timelapse_batches.id", ondelete="CASCADE"), nullable=False
    )
    image_id = Column(
        BigInteger, ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    sequence_order = Column(Integer, nullable=False)
    included_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    timelapse_batch = relationship("TimelapseBatch", back_populates="timelapse_images")
    image = relationship("Image", back_populates="timelapse_images")

    # Constraints
    __table_args__ = (
        UniqueConstraint("timelapse_batch_id", "image_id", name="uq_batch_image"),
        UniqueConstraint(
            "timelapse_batch_id", "sequence_order", name="uq_batch_sequence"
        ),
        Index("idx_timelapse_images_batch", "timelapse_batch_id"),
        Index("idx_timelapse_images_image", "image_id"),
        Index("idx_timelapse_images_sequence", "timelapse_batch_id", "sequence_order"),
    )

    def __repr__(self):
        return f"<TimelapseImage(batch_id={self.timelapse_batch_id}, image_id={self.image_id}, order={self.sequence_order})>"


class CaptureAttempt(Base):
    """Capture attempt tracking table"""

    __tablename__ = "capture_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(
        Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    attempted_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)
    status = Column(String(20), nullable=False)
    image_id = Column(
        BigInteger, ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Relationships
    camera = relationship("Camera", back_populates="capture_attempts")
    image = relationship("Image", back_populates="capture_attempt")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'failed', 'timeout', 'error')",
            name="check_capture_status",
        ),
        CheckConstraint("retry_count >= 0", name="check_retry_count_non_negative"),
        Index("idx_capture_attempts_camera_time", "camera_id", "attempted_at"),
        Index("idx_capture_attempts_status", "status"),
    )

    def __repr__(self):
        return f"<CaptureAttempt(id={self.id}, camera_id={self.camera_id}, status='{self.status}')>"


class Share(Base):
    """Video sharing system table"""

    __tablename__ = "shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share_token = Column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    share_type = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    download_enabled = Column(Boolean, default=False, nullable=False)
    embed_enabled = Column(Boolean, default=False, nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    share_metadata = Column(JSONB, default={}, nullable=False)
    search_vector = Column(TSVECTOR, nullable=True)
    view_count = Column(Integer, default=0, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    share_batches = relationship(
        "ShareBatch", back_populates="share", cascade="all, delete-orphan"
    )
    share_customization = relationship(
        "ShareCustomization",
        back_populates="share",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "share_type IN ('video_only', 'info_page', 'gallery')",
            name="check_share_type",
        ),
        CheckConstraint("view_count >= 0", name="check_view_count_non_negative"),
        Index("idx_shares_token", "share_token"),
        Index("idx_shares_active", "is_active", "expires_at"),
        Index(
            "idx_shares_metadata_gin",
            "share_metadata",
            postgresql_using="gin",
            postgresql_where=text("share_metadata != '{}'::jsonb"),
        ),
        Index("idx_shares_search", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self):
        return f"<Share(id={self.id}, title='{self.title}', type='{self.share_type}')>"


class ShareBatch(Base):
    """Junction table linking shares to timelapse batches"""

    __tablename__ = "share_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share_id = Column(
        Integer, ForeignKey("shares.id", ondelete="CASCADE"), nullable=False
    )
    timelapse_batch_id = Column(
        Integer, ForeignKey("timelapse_batches.id", ondelete="CASCADE"), nullable=False
    )
    display_order = Column(Integer, default=1, nullable=False)
    custom_title = Column(String(255), nullable=True)
    show_metadata = Column(Boolean, default=True, nullable=False)
    added_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    share = relationship("Share", back_populates="share_batches")
    timelapse_batch = relationship("TimelapseBatch", back_populates="share_batches")

    # Constraints
    __table_args__ = (
        UniqueConstraint("share_id", "timelapse_batch_id", name="uq_share_batch"),
        Index("idx_share_batches_share", "share_id", "display_order"),
        Index("idx_share_batches_batch", "timelapse_batch_id"),
    )

    def __repr__(self):
        return f"<ShareBatch(share_id={self.share_id}, batch_id={self.timelapse_batch_id})>"


class ShareCustomization(Base):
    """Share appearance customization table"""

    __tablename__ = "share_customization"

    id = Column(Integer, primary_key=True, autoincrement=True)
    share_id = Column(
        Integer, ForeignKey("shares.id", ondelete="CASCADE"), nullable=False
    )
    theme_config = Column(
        JSONB,
        default={
            "primary_color": "#007bff",
            "secondary_color": "#6c757d",
            "background_color": "#ffffff",
            "text_color": "#333333",
        },
        nullable=False,
    )
    display_options = Column(
        JSONB,
        default={
            "show_camera_info": True,
            "show_day_counter": True,
            "show_date_range": True,
            "show_technical_info": False,
            "show_generation_time": False,
            "layout": "grid",
        },
        nullable=False,
    )
    created_at = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    # Relationships
    share = relationship("Share", back_populates="share_customization")

    def __repr__(self):
        return f"<ShareCustomization(id={self.id}, share_id={self.share_id})>"


# Database triggers and functions (PostgreSQL specific)


# Auto-update trigger for cameras.updated_at
@event.listens_for(Camera, "before_update")
def camera_update_timestamp(mapper, connection, target):
    """Update the updated_at timestamp on camera updates"""
    target.updated_at = func.now()


# Auto-calculate day number trigger for images
@event.listens_for(Image, "before_insert")
def calculate_day_number(mapper, connection, target):
    """Calculate day number based on camera start date"""
    if target.day_number is None and target.camera_id:
        # TODO: This will need to be implemented with a database function in production. Right now we handle this in the application layer
        pass


# Search vector update trigger for shares
@event.listens_for(Share, "before_insert")
@event.listens_for(Share, "before_update")
def update_search_vector(mapper, connection, target):
    """Update search vector for full-text search"""
    if target.title or target.description:
        # TODO: This will use PostgreSQL's to_tsvector function in production
        pass
