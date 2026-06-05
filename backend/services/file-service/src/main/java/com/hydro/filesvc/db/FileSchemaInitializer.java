// file-service 数据库结构兜底初始化。
// Docker 初始化 SQL 只在空库首次执行；这里用于已有数据库的平滑升级。
package com.hydro.filesvc.db;

import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class FileSchemaInitializer {

    private final JdbcTemplate jdbcTemplate;

    // 注入 JdbcTemplate，用于执行幂等 DDL 和兼容性字段补齐。
    public FileSchemaInitializer(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    // 服务启动时确保 file_asset 表和新字段存在；数据库不可用时保持服务可启动。
    @PostConstruct
    public void initializeSchema() {
        try {
            jdbcTemplate.execute("""
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
                    )
                    """);
            addColumnIfMissing("file_type", "VARCHAR(32) NOT NULL DEFAULT 'generic'");
            addColumnIfMissing("checksum_sha256", "CHAR(64) NOT NULL DEFAULT ''");
        } catch (Exception ignored) {
            // 数据库短暂不可用时不阻断服务启动，上传流程仍会在运行期暴露明确错误或走内存兜底。
        }
    }

    // 旧库缺字段时尝试补齐；字段已存在时 MySQL 会报错，这里静默忽略即可。
    private void addColumnIfMissing(String columnName, String definition) {
        try {
            jdbcTemplate.execute("ALTER TABLE file_asset ADD COLUMN " + columnName + " " + definition);
        } catch (Exception ignored) {
            // 字段已存在或数据库暂不可用时无需重复处理。
        }
    }
}
