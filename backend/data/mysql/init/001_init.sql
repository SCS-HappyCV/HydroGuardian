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

USE file_service_db;

CREATE TABLE IF NOT EXISTS file_asset (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    file_id VARCHAR(64) NOT NULL UNIQUE,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    object_key VARCHAR(255) NOT NULL,
    size BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
