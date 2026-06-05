// MinIO 对象存储客户端封装。
// 负责 bucket 初始化、对象写入、校验和计算以及下载地址生成。
package com.hydro.filesvc.storage;

import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.GetPresignedObjectUrlArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.http.Method;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

@Service
public class MinioObjectStorage {

    private final MinioClient minioClient;
    private final MinioClient publicMinioClient;
    private final String bucket;
    private final String publicEndpoint;
    private final int presignedExpirySeconds;
    private volatile boolean bucketReady;

    // 注入 MinIO 客户端、bucket 名称、对外访问 endpoint 和预签名 URL 过期时间。
    public MinioObjectStorage(
            MinioClient minioClient,
            @Value("${app.minio.bucket}") String bucket,
            @Value("${app.minio.public-endpoint:}") String publicEndpoint,
            @Value("${app.minio.endpoint}") String internalEndpoint,
            @Value("${app.minio.access-key}") String accessKey,
            @Value("${app.minio.secret-key}") String secretKey,
            @Value("${app.minio.presigned-expiry-seconds:604800}") int presignedExpirySeconds
    ) {
        this.minioClient = minioClient;
        this.bucket = bucket;
        this.publicEndpoint = trimTrailingSlash(publicEndpoint == null || publicEndpoint.isBlank()
                ? internalEndpoint
                : publicEndpoint);
        this.publicMinioClient = MinioClient.builder()
                .endpoint(this.publicEndpoint)
                .credentials(accessKey, secretKey)
                .build();
        this.presignedExpirySeconds = presignedExpirySeconds;
    }

    // 写入对象并返回可持久化摘要。
    public StoredObject putObject(String objectKey, String contentType, byte[] content) {
        try {
            ensureBucket();
            byte[] payload = content == null ? new byte[0] : content;
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(objectKey)
                    .contentType(contentType == null || contentType.isBlank() ? "application/octet-stream" : contentType)
                    .stream(new ByteArrayInputStream(payload), payload.length, -1)
                    .build());
            return new StoredObject(objectKey, buildDownloadUrl(objectKey), sha256(payload), payload.length);
        } catch (Exception exc) {
            throw new IllegalStateException("failed to upload object to MinIO", exc);
        }
    }

    // 根据已保存的 objectKey 重新生成下载地址，供查询接口使用。
    public String downloadUrlFor(String objectKey) {
        if (objectKey == null || objectKey.isBlank()) {
            return "";
        }
        return buildDownloadUrl(objectKey);
    }

    // 从 MinIO 读取对象内容，供后端服务通过 gRPC 获取结构化资产。
    public byte[] getObject(String objectKey) {
        try (var stream = minioClient.getObject(GetObjectArgs.builder()
                .bucket(bucket)
                .object(objectKey)
                .build())) {
            return stream.readAllBytes();
        } catch (Exception exc) {
            throw new IllegalStateException("failed to download object from MinIO", exc);
        }
    }

    // 首次上传前确保 bucket 存在；成功后用内存标记避免每次重复检查。
    private void ensureBucket() throws Exception {
        if (bucketReady) {
            return;
        }
        synchronized (this) {
            if (bucketReady) {
                return;
            }
            boolean exists = minioClient.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!exists) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
            }
            bucketReady = true;
        }
    }

    // 生成预签名下载 URL，避免要求 bucket 开启公共读权限。
    private String buildDownloadUrl(String objectKey) {
        try {
            return publicMinioClient.getPresignedObjectUrl(GetPresignedObjectUrlArgs.builder()
                    .method(Method.GET)
                    .bucket(bucket)
                    .object(objectKey)
                    .expiry(presignedExpirySeconds)
                    .build());
        } catch (Exception ignored) {
            // 预签名失败时返回可读的直连 URL，便于排查 objectKey 和 endpoint 配置。
            return publicEndpoint + "/" + bucket + "/" + objectKey;
        }
    }

    // 计算文件内容 SHA-256，后续可用于样本资产去重和完整性校验。
    private String sha256(byte[] payload) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(payload));
        } catch (NoSuchAlgorithmException exc) {
            throw new IllegalStateException("SHA-256 algorithm is unavailable", exc);
        }
    }

    // 去掉 endpoint 末尾斜杠，避免拼 URL 时出现双斜杠。
    private String trimTrailingSlash(String value) {
        if (value == null || value.isBlank()) {
            return "";
        }
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
