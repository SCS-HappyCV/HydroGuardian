// case-service 数据库结构兜底初始化。
// init SQL 只在 MySQL 首次初始化时执行；该组件用于已存在数据库的平滑升级。
package com.hydro.casehub.db;

import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class CaseSchemaInitializer {

    private final JdbcTemplate jdbcTemplate;

    // 注入 JdbcTemplate，用于执行幂等 DDL。
    public CaseSchemaInitializer(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    // 服务启动时创建缺失的 agent 结果表，避免旧数据库缺表。
    @PostConstruct
    public void initializeSchema() {
        try {
            jdbcTemplate.execute("""
                    CREATE TABLE IF NOT EXISTS case_agent_result (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        case_id VARCHAR(64) NOT NULL UNIQUE,
                        agent_result_json JSON NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_case_agent_result_case_id (case_id)
                    )
                    """);
        } catch (Exception ignored) {
            // 数据库短暂不可用时保持服务可启动，运行期仍会沿用原有内存兜底策略。
        }
    }
}
