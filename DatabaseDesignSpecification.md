# UniFi Timelapser Database Design Specification

## 🎯 Primary Objectives

### Core Goals

- Track all captured images with metadata for efficient querying and cleanup
- Manage timelapse generation batches with complete traceability of which images
  were included
- Support multiple generation modes (continuous, checkpoint, manual) with
  different retention policies
- Enable day counting overlays with flexible positioning and styling options
- Maintain security by hashing sensitive camera URL information
- Provide audit trail for troubleshooting and analytics

### Functional Requirements

- Multi-camera support with individual configuration per camera
- Relational tracking between images and timelapse batches for complete
  traceability
- Flexible cleanup policies based on age, batch inclusion, and generation modes
- Status tracking for async timelapse generation processes
- Day progression tracking for educational/documentary timelapses
- Performance optimization for frequent image ingestion and batch queries

## 📋 Implementation Instructions

### Database Setup

- Use SQLite for simplicity and portability (consistent with current codebase)
- Implement foreign key constraints to maintain referential integrity
- Add indexes on frequently queried columns (camera_id, captured_at, status)
- Use transactions for batch operations to ensure consistency

### Security Guidelines

- Hash all camera URLs using SHA-256 before database storage
- Store actual URLs in environment variables or encrypted configuration files
- Never log or expose hashed URLs in application output
- Implement database file permissions to restrict access

### Data Lifecycle Management

- Auto-calculate day numbers when inserting images based on camera start date
- Cascade delete timelapse_images when parent batch is deleted
- Implement cleanup routines to remove old images not referenced by active
  batches
- Validate data integrity before processing timelapse batches

### Tech Stack

FastAPI + Pydantic + SQLAlchemy + Alembic + Postgres

## 🗄️ Complete Database Structure

### 1. cameras Table

```sql
CREATE TABLE cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) UNIQUE NOT NULL,
    url_hash VARCHAR(64) UNIQUE NOT NULL,
    encryption_key_ref VARCHAR(64),
    last_health_check TIMESTAMP,
    connection_failures INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,
    rotation VARCHAR(20) DEFAULT 'none' CHECK(rotation IN ('none', 'left', 'right', 'invert')),
    day_counter_enabled BOOLEAN DEFAULT FALSE,
    day_counter_start_date DATE,
    metadata JSONB DEFAULT '{}',  -- Extensible metadata
    day_overlay_position VARCHAR(20) DEFAULT 'top-right' CHECK(day_overlay_position IN ('top-left', 'top-right', 'bottom-left', 'bottom-right')),
    day_overlay_style JSON DEFAULT '{"font_size": 24, "font_color": "#FFFFFF", "background_color": "#000000", "background_opacity": 0.7, "font_family": "Arial"}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 2. images Table

```sql
CREATE TABLE images (
    id BIGSERIAL PRIMARY KEY AUTOINCREMENT,  -- Better for high volume
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,  -- Support larger files
    width INTEGER,
    height INTEGER,
    format VARCHAR(10) NOT NULL,
    quality_score INTEGER CHECK(quality_score BETWEEN 0 AND 100),
    file_hash VARCHAR(64),
    captured_at TIMESTAMPTZ NOT NULL,  -- Timezone-aware
    day_number INTEGER,
    processing_metadata JSONB DEFAULT '{}',  -- EXIF data, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3. timelapse_batches Table

```sql
CREATE TABLE timelapse_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    batch_type VARCHAR(20) NOT NULL CHECK(batch_type IN ('continuous', 'checkpoint', 'manual')),
    status VARCHAR(20) DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    output_filename VARCHAR(255),
    output_path TEXT,
    file_size_bytes INTEGER,
    frame_rate INTEGER DEFAULT 30,
    total_frames INTEGER DEFAULT 0,
    duration_seconds FLOAT,
    generation_mode VARCHAR(20) NOT NULL CHECK(generation_mode IN ('every_capture', 'periodic', 'manual_only')),
    day_overlay_applied BOOLEAN DEFAULT FALSE,
    day_range_start INTEGER,
    day_range_end INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
);
```

### 4. timelapse_images Table (Junction Table)

```sql
CREATE TABLE timelapse_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timelapse_batch_id INTEGER NOT NULL,
    image_id INTEGER NOT NULL,
    sequence_order INTEGER NOT NULL,
    included_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (timelapse_batch_id) REFERENCES timelapse_batches(id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
    UNIQUE(timelapse_batch_id, image_id),
    UNIQUE(timelapse_batch_id, sequence_order)
);
```

###5. Database Indexes

```sql
-- PostgreSQL-specific performance indexes
CREATE INDEX idx_images_camera_captured_desc ON images(camera_id, captured_at DESC);
CREATE INDEX idx_images_captured_at_brin ON images USING BRIN(captured_at);  -- Time-series optimization
CREATE INDEX idx_images_metadata_gin ON images USING GIN(processing_metadata);  -- JSON queries
CREATE INDEX idx_cameras_overlay_gin ON cameras USING GIN(day_overlay_style);
CREATE INDEX idx_shares_metadata_gin ON shares USING GIN(metadata) WHERE metadata != '{}';

-- Full-text search for shares
CREATE INDEX idx_shares_search ON shares USING GIN(to_tsvector('english', title || ' ' || COALESCE(description, '')));
```

### 6. Additional Indexes

```sql
-- For cleanup queries
CREATE INDEX idx_images_captured_at ON images(captured_at);
CREATE INDEX idx_images_orphaned ON images(id) WHERE id NOT IN (SELECT image_id FROM timelapse_images);

-- For day counter queries
CREATE INDEX idx_images_camera_day ON images(camera_id, day_number);

-- For batch processing
CREATE INDEX idx_batches_pending ON timelapse_batches(status, created_at) WHERE status = 'pending';
```

### 7. Capture Attempt Tracking

```sql
CREATE TABLE capture_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK(status IN ('success', 'failed', 'timeout', 'error')),
    image_id INTEGER,  -- NULL if failed
    error_message TEXT,
    duration_ms INTEGER,
    retry_count INTEGER DEFAULT 0,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE SET NULL
);
```

### 8. Sharing System

####Shares table

```sql
CREATE TABLE shares (
    id SERIAL PRIMARY KEY,
    share_token UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,  -- Native UUID
    title VARCHAR(255) NOT NULL,
    description TEXT,
    share_type VARCHAR(20) NOT NULL CHECK(share_type IN ('video_only', 'info_page', 'gallery')),
    is_active BOOLEAN DEFAULT TRUE,
    download_enabled BOOLEAN DEFAULT FALSE,
    embed_enabled BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',  -- Extensible share metadata
    search_vector TSVECTOR,  -- Full-text search
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update search vector
CREATE TRIGGER shares_search_vector_update
    BEFORE INSERT OR UPDATE ON shares
    FOR EACH ROW EXECUTE FUNCTION
    tsvector_update_trigger(search_vector, 'pg_catalog.english', title, description);
```

####Share batches junction table

```sql
CREATE TABLE share_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_id INTEGER NOT NULL,
    timelapse_batch_id INTEGER NOT NULL,
    display_order INTEGER DEFAULT 1,
    custom_title VARCHAR(255),
    show_metadata BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (share_id) REFERENCES shares(id) ON DELETE CASCADE,
    FOREIGN KEY (timelapse_batch_id) REFERENCES timelapse_batches(id) ON DELETE CASCADE,
    UNIQUE(share_id, timelapse_batch_id)
);
```

####Share customization

```sql
CREATE TABLE share_customization (
    id SERIAL PRIMARY KEY,
    share_id INTEGER NOT NULL REFERENCES shares(id) ON DELETE CASCADE,
    theme_config JSONB DEFAULT '{
        "primary_color": "#007bff",
    }',
    display_options JSONB DEFAULT '{
        "show_camera_info": true,
        "show_day_counter": true,
        "show_date_range": true,
        "show_technical_info": false,
        "show_generation_time": false,
        "layout": "grid"
    }',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (share_id) REFERENCES shares(id) ON DELETE CASCADE
);
```

####Indexes

```sql
CREATE INDEX idx_shares_token ON shares(share_token);
CREATE INDEX idx_shares_active ON shares(is_active, expires_at);
CREATE INDEX idx_share_batches_share ON share_batches(share_id, display_order);
```

#### Basic Video Share:

```sql
-- Create simple video share
INSERT INTO shares (share_token, title, share_type)
VALUES ('abc123def456', 'Construction Day 45', 'video_only');

INSERT INTO share_batches (share_id, timelapse_batch_id)
VALUES (last_insert_rowid(), 456);
```

#### Info Page with Multiple Videos:

```sql
-- Create info page with multiple timelapses
INSERT INTO shares (share_token, title, description, share_type, download_enabled)
VALUES ('project2024', 'Office Construction 2024',
        'Complete construction timeline', 'info_page', TRUE);

-- Add multiple batches in order
INSERT INTO share_batches (share_id, timelapse_batch_id, display_order, custom_title) VALUES
(last_insert_rowid(), 456, 1, 'Foundation Work'),
(last_insert_rowid(), 457, 2, 'Framing'),
(last_insert_rowid(), 458, 3, 'Finishing Work');

-- Customize appearance
INSERT INTO share_customization (share_id, primary_color, show_day_counter)
VALUES (last_insert_rowid(), '#ff6b35', TRUE);
```

#### Clean URL Structure

```md
# Simple video share

https://timelapser.example.com/share/abc123def456

# Info page

https://timelapser.example.com/share/project2024

# Embed player

https://timelapser.example.com/embed/abc123def456

# Direct download (if enabled)

https://timelapser.example.com/share/abc123def456/download
```

#### Basic Queries

```sql
-- Get share with all batches
SELECT s.*, sb.custom_title, tb.output_filename
FROM shares s
JOIN share_batches sb ON s.id = sb.share_id
JOIN timelapse_batches tb ON sb.timelapse_batch_id = tb.id
WHERE s.share_token = ? AND s.is_active = TRUE
ORDER BY sb.display_order;

-- Check if share is valid and not expired
SELECT * FROM shares
WHERE share_token = ?
  AND is_active = TRUE
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP);

-- Increment view count
UPDATE shares SET view_count = view_count + 1
WHERE share_token = ?;
```

### 9. Database Triggers

```sql
-- Auto-update cameras.updated_at on changes
CREATE TRIGGER update_cameras_timestamp
    AFTER UPDATE ON cameras
    BEGIN
        UPDATE cameras SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
    END;
```

```sql
-- Auto-calculate day_number on image insert/update
CREATE TRIGGER calculate_day_number
    AFTER INSERT ON images
    WHEN NEW.day_number IS NULL
    BEGIN
        UPDATE images
        SET day_number = (
            SELECT CASE
                WHEN c.day_counter_enabled = TRUE AND c.day_counter_start_date IS NOT NULL
                THEN CAST(julianday(date(NEW.captured_at)) - julianday(c.day_counter_start_date) AS INTEGER) + 1
                ELSE NULL
            END
            FROM cameras c WHERE c.id = NEW.camera_id
        )
        WHERE id = NEW.id;
    END;
```

## 🔗 Key Features For Video Shares

### 🎬 Video-Only Shares

```sql
-- Simple direct video link
INSERT INTO shares (share_token, title, share_type, access_type)
VALUES ('abc123def456', 'Construction Day 45', 'video_only', 'public');

INSERT INTO share_batches (share_id, timelapse_batch_id)
VALUES (LAST_INSERT_ROWID(), 456);
```

### 📊 Rich Info Pages

```sql
-- Comprehensive project page
INSERT INTO shares (share_token, title, description, share_type, creator_name)
VALUES ('xyz789uvw012', 'Office Construction Project',
        'Follow our 6-month construction journey...', 'info_page', 'Jordan L.');

-- Customize the look
INSERT INTO share_customization (share_id, theme, primary_color, show_day_counter)
VALUES (LAST_INSERT_ROWID(), 'dark', '#ff6b35', TRUE);
```

## 📊 Key Relationships

- **`cameras` → `images`** (1:many) - Each camera captures multiple images
- **`cameras` → `timelapse_batches`** (1:many) - Each camera can have multiple
  timelapse batches
- **`images` ↔ `timelapse_batches`** (many:many via timelapse_images) - Images
  can be included in multiple batches
- **`timelapse_batches` → `timelapse_images`** (1:many) - Each batch contains
  multiple image references

## ⚡ Performance Considerations

- Strategic indexes on query-heavy columns
- Batch processing support with status tracking
- Cleanup optimization with safe-delete queries
