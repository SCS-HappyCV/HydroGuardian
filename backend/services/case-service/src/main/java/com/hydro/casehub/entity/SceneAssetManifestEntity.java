// 场景资产清单表实体。
// 该表把 scene_id 映射到 file-service 中的预处理样本、图像和点云文件资产。
package com.hydro.casehub.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

@TableName("scene_asset_manifest")
public class SceneAssetManifestEntity {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("scene_id")
    private String sceneId;

    @TableField("sample_id")
    private String sampleId;

    @TableField("scene_sample_file_id")
    private String sceneSampleFileId;

    @TableField("image_file_id")
    private String imageFileId;

    @TableField("point_cloud_file_id")
    private String pointCloudFileId;

    @TableField("pre_image_file_id")
    private String preImageFileId;

    @TableField("post_image_file_id")
    private String postImageFileId;

    @TableField("preprocess_version")
    private String preprocessVersion;

    @TableField("checksum_sha256")
    private String checksumSha256;

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

    // 返回场景业务 ID。
    public String getSceneId() {
        return sceneId;
    }

    // 设置场景业务 ID。
    public void setSceneId(String sceneId) {
        this.sceneId = sceneId;
    }

    // 返回预处理样本 ID。
    public String getSampleId() {
        return sampleId;
    }

    // 设置预处理样本 ID。
    public void setSampleId(String sampleId) {
        this.sampleId = sampleId;
    }

    // 返回 SceneTensorSample JSON 的 fileId。
    public String getSceneSampleFileId() {
        return sceneSampleFileId;
    }

    // 设置 SceneTensorSample JSON 的 fileId。
    public void setSceneSampleFileId(String sceneSampleFileId) {
        this.sceneSampleFileId = sceneSampleFileId;
    }

    // 返回正射图或主图像 fileId。
    public String getImageFileId() {
        return imageFileId;
    }

    // 设置正射图或主图像 fileId。
    public void setImageFileId(String imageFileId) {
        this.imageFileId = imageFileId;
    }

    // 返回点云文件 fileId。
    public String getPointCloudFileId() {
        return pointCloudFileId;
    }

    // 设置点云文件 fileId。
    public void setPointCloudFileId(String pointCloudFileId) {
        this.pointCloudFileId = pointCloudFileId;
    }

    // 返回变化检测前时相图像 fileId。
    public String getPreImageFileId() {
        return preImageFileId;
    }

    // 设置变化检测前时相图像 fileId。
    public void setPreImageFileId(String preImageFileId) {
        this.preImageFileId = preImageFileId;
    }

    // 返回变化检测后时相图像 fileId。
    public String getPostImageFileId() {
        return postImageFileId;
    }

    // 设置变化检测后时相图像 fileId。
    public void setPostImageFileId(String postImageFileId) {
        this.postImageFileId = postImageFileId;
    }

    // 返回预处理流水线版本。
    public String getPreprocessVersion() {
        return preprocessVersion;
    }

    // 设置预处理流水线版本。
    public void setPreprocessVersion(String preprocessVersion) {
        this.preprocessVersion = preprocessVersion;
    }

    // 返回清单或样本摘要校验和。
    public String getChecksumSha256() {
        return checksumSha256;
    }

    // 设置清单或样本摘要校验和。
    public void setChecksumSha256(String checksumSha256) {
        this.checksumSha256 = checksumSha256;
    }

    // 返回清单协议版本。
    public String getSchemaVersion() {
        return schemaVersion;
    }

    // 设置清单协议版本。
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
