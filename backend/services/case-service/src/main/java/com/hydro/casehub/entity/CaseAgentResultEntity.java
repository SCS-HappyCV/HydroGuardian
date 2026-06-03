// case_agent_result 表实体。
// 该表用于保存 agent-service 生成的完整执行快照，支撑证据链回放和调试追踪。
package com.hydro.casehub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

@TableName("case_agent_result")
public class CaseAgentResultEntity {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("case_id")
    private String caseId;

    @TableField("agent_result_json")
    private String agentResultJson;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;

    // 返回数据库自增主键。
    public Long getId() {
        return id;
    }

    // 设置数据库自增主键。
    public void setId(Long id) {
        this.id = id;
    }

    // 返回关联的 case id。
    public String getCaseId() {
        return caseId;
    }

    // 设置关联的 case id。
    public void setCaseId(String caseId) {
        this.caseId = caseId;
    }

    // 返回完整 agent 执行快照 JSON。
    public String getAgentResultJson() {
        return agentResultJson;
    }

    // 设置完整 agent 执行快照 JSON。
    public void setAgentResultJson(String agentResultJson) {
        this.agentResultJson = agentResultJson;
    }

    // 返回创建时间。
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    // 设置创建时间。
    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    // 返回更新时间。
    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    // 设置更新时间。
    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
