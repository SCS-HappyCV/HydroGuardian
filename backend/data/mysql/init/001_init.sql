CREATE DATABASE IF NOT EXISTS case_service_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS file_service_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS agent_service_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'hydro'@'%' IDENTIFIED BY 'hydro123';
GRANT ALL PRIVILEGES ON case_service_db.* TO 'hydro'@'%';
GRANT ALL PRIVILEGES ON file_service_db.* TO 'hydro'@'%';
GRANT ALL PRIVILEGES ON agent_service_db.* TO 'hydro'@'%';
FLUSH PRIVILEGES;

USE case_service_db;

CREATE TABLE IF NOT EXISTS risk_case (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    task_text TEXT NOT NULL,
    scene_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    risk_level VARCHAR(16),
    assignee VARCHAR(64),
    tags JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_agent_result (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    case_id VARCHAR(64) NOT NULL UNIQUE,
    agent_result_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_case_agent_result_case_id (case_id)
);

CREATE TABLE IF NOT EXISTS case_work_order (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    work_order_id VARCHAR(64) NOT NULL UNIQUE,
    case_id VARCHAR(64) NOT NULL,
    risk_card_id VARCHAR(64),
    risk_type VARCHAR(128),
    risk_level VARCHAR(32),
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    recommended_action TEXT,
    status VARCHAR(32) NOT NULL,
    assignee VARCHAR(64),
    deadline VARCHAR(64),
    closure_note TEXT,
    evidence_summary_json JSON,
    schema_version VARCHAR(64) NOT NULL DEFAULT 'case_work_order.v1',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_case_work_order_case_id (case_id),
    INDEX idx_case_work_order_status (status),
    INDEX idx_case_work_order_assignee (assignee)
);

CREATE TABLE IF NOT EXISTS scene_asset_manifest (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    scene_id VARCHAR(128) NOT NULL UNIQUE,
    sample_id VARCHAR(128) NOT NULL,
    scene_sample_file_id VARCHAR(64) NOT NULL,
    image_file_id VARCHAR(64),
    point_cloud_file_id VARCHAR(64),
    pre_image_file_id VARCHAR(64),
    post_image_file_id VARCHAR(64),
    preprocess_version VARCHAR(64),
    checksum_sha256 CHAR(64),
    schema_version VARCHAR(64) NOT NULL DEFAULT 'scene_asset_manifest.v1',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_scene_asset_manifest_scene_id (scene_id),
    INDEX idx_scene_asset_manifest_sample_id (sample_id)
);

USE file_service_db;

CREATE TABLE IF NOT EXISTS file_asset (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    file_id VARCHAR(64) NOT NULL UNIQUE,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    object_key VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL DEFAULT 'generic',
    checksum_sha256 CHAR(64) NOT NULL DEFAULT '',
    size BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
