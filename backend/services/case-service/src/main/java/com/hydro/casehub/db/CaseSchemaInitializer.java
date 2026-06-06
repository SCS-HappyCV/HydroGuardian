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

    // 服务启动时创建缺失的扩展表，避免旧数据库缺表。
    @PostConstruct
    public void initializeSchema() {
        createCaseAgentResultTable();
        createCaseWorkOrderTable();
        createSceneAssetManifestTable();
    }

    // 创建 agent 执行快照表，保存完整闭环结果。
    private void createCaseAgentResultTable() {
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

    // 创建工单表，保存智能体生成的真实处置闭环记录。
    private void createCaseWorkOrderTable() {
        try {
            jdbcTemplate.execute("""
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
                    )
                    """);
        } catch (Exception ignored) {
            // 数据库短暂不可用时保持服务可启动；gRPC 层会写入内存兜底缓存。
        }
    }

    // 创建场景资产清单表，保存 scene_id 到 file-service fileId 的稳定映射。
    private void createSceneAssetManifestTable() {
        try {
            jdbcTemplate.execute("""
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
                    )
                    """);
        } catch (Exception ignored) {
            // 数据库短暂不可用时保持服务可启动；gRPC 层会写入内存兜底缓存。
        }
    }
}
