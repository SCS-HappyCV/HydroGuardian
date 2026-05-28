USE case_service_db;

CREATE TABLE IF NOT EXISTS app_user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role_id VARCHAR(64),
    role_code VARCHAR(64),
    department VARCHAR(128),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    avatar_url VARCHAR(512),
    last_login_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_app_user_role_id (role_id),
    INDEX idx_app_user_status (status),
    INDEX idx_app_user_created_at (created_at)
);
