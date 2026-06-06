// 工单表实体。
// 该实体保存由 agent-service 风险结果生成的现场复核或处置工单。
package com.hydro.casehub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

@TableName("case_work_order")
public class CaseWorkOrderEntity {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("work_order_id")
    private String workOrderId;

    @TableField("case_id")
    private String caseId;

    @TableField("risk_card_id")
    private String riskCardId;

    @TableField("risk_type")
    private String riskType;

    @TableField("risk_level")
    private String riskLevel;

    @TableField("title")
    private String title;

    @TableField("summary")
    private String summary;

    @TableField("recommended_action")
    private String recommendedAction;

    @TableField("status")
    private String status;

    @TableField("assignee")
    private String assignee;

    @TableField("deadline")
    private String deadline;

    @TableField("closure_note")
    private String closureNote;

    @TableField("evidence_summary_json")
    private String evidenceSummaryJson;

    @TableField("schema_version")
    private String schemaVersion;

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

    // 返回工单业务 ID。
    public String getWorkOrderId() {
        return workOrderId;
    }

    // 设置工单业务 ID。
    public void setWorkOrderId(String workOrderId) {
        this.workOrderId = workOrderId;
    }

    // 返回关联 case ID。
    public String getCaseId() {
        return caseId;
    }

    // 设置关联 case ID。
    public void setCaseId(String caseId) {
        this.caseId = caseId;
    }

    // 返回风险卡 ID。
    public String getRiskCardId() {
        return riskCardId;
    }

    // 设置风险卡 ID。
    public void setRiskCardId(String riskCardId) {
        this.riskCardId = riskCardId;
    }

    // 返回风险类型。
    public String getRiskType() {
        return riskType;
    }

    // 设置风险类型。
    public void setRiskType(String riskType) {
        this.riskType = riskType;
    }

    // 返回风险等级。
    public String getRiskLevel() {
        return riskLevel;
    }

    // 设置风险等级。
    public void setRiskLevel(String riskLevel) {
        this.riskLevel = riskLevel;
    }

    // 返回工单标题。
    public String getTitle() {
        return title;
    }

    // 设置工单标题。
    public void setTitle(String title) {
        this.title = title;
    }

    // 返回工单摘要。
    public String getSummary() {
        return summary;
    }

    // 设置工单摘要。
    public void setSummary(String summary) {
        this.summary = summary;
    }

    // 返回建议动作。
    public String getRecommendedAction() {
        return recommendedAction;
    }

    // 设置建议动作。
    public void setRecommendedAction(String recommendedAction) {
        this.recommendedAction = recommendedAction;
    }

    // 返回工单状态。
    public String getStatus() {
        return status;
    }

    // 设置工单状态。
    public void setStatus(String status) {
        this.status = status;
    }

    // 返回负责人。
    public String getAssignee() {
        return assignee;
    }

    // 设置负责人。
    public void setAssignee(String assignee) {
        this.assignee = assignee;
    }

    // 返回截止时间文本。
    public String getDeadline() {
        return deadline;
    }

    // 设置截止时间文本。
    public void setDeadline(String deadline) {
        this.deadline = deadline;
    }

    // 返回关闭说明。
    public String getClosureNote() {
        return closureNote;
    }

    // 设置关闭说明。
    public void setClosureNote(String closureNote) {
        this.closureNote = closureNote;
    }

    // 返回证据摘要 JSON。
    public String getEvidenceSummaryJson() {
        return evidenceSummaryJson;
    }

    // 设置证据摘要 JSON。
    public void setEvidenceSummaryJson(String evidenceSummaryJson) {
        this.evidenceSummaryJson = evidenceSummaryJson;
    }

    // 返回协议版本。
    public String getSchemaVersion() {
        return schemaVersion;
    }

    // 设置协议版本。
    public void setSchemaVersion(String schemaVersion) {
        this.schemaVersion = schemaVersion;
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
