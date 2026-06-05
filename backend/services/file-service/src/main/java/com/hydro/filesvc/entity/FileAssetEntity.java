// file_asset 表实体。
// 记录文件在 MinIO 中的对象键、类型、校验和等资产元数据。
package com.hydro.filesvc.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import java.time.LocalDateTime;

@TableName("file_asset")
public class FileAssetEntity {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("file_id")
    private String fileId;

    @TableField("file_name")
    private String fileName;

    @TableField("content_type")
    private String contentType;

    @TableField("object_key")
    private String objectKey;

    @TableField("file_type")
    private String fileType;

    @TableField("checksum_sha256")
    private String checksumSha256;

    @TableField("size")
    private Long size;

    @TableField("created_at")
    private LocalDateTime createdAt;

    // 返回数据库自增主键。
    public Long getId() {
        return id;
    }

    // 设置数据库自增主键。
    public void setId(Long id) {
        this.id = id;
    }

    // 返回文件资产 ID。
    public String getFileId() {
        return fileId;
    }

    // 设置文件资产 ID。
    public void setFileId(String fileId) {
        this.fileId = fileId;
    }

    // 返回原始文件名。
    public String getFileName() {
        return fileName;
    }

    // 设置原始文件名。
    public void setFileName(String fileName) {
        this.fileName = fileName;
    }

    // 返回文件 MIME 类型。
    public String getContentType() {
        return contentType;
    }

    // 设置文件 MIME 类型。
    public void setContentType(String contentType) {
        this.contentType = contentType;
    }

    // 返回 MinIO 对象键。
    public String getObjectKey() {
        return objectKey;
    }

    // 设置 MinIO 对象键。
    public void setObjectKey(String objectKey) {
        this.objectKey = objectKey;
    }

    // 返回业务文件类型，例如 image 或 point_cloud。
    public String getFileType() {
        return fileType;
    }

    // 设置业务文件类型。
    public void setFileType(String fileType) {
        this.fileType = fileType;
    }

    // 返回文件内容 SHA-256 校验和。
    public String getChecksumSha256() {
        return checksumSha256;
    }

    // 设置文件内容 SHA-256 校验和。
    public void setChecksumSha256(String checksumSha256) {
        this.checksumSha256 = checksumSha256;
    }

    // 返回文件字节大小。
    public Long getSize() {
        return size;
    }

    // 设置文件字节大小。
    public void setSize(Long size) {
        this.size = size;
    }

    // 返回创建时间。
    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    // 设置创建时间。
    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
