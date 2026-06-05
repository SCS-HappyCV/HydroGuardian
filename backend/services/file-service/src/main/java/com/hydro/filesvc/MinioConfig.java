// MinIO 客户端配置。
// 使用内部 endpoint 连接对象存储，下载展示地址由 storage 层按 public-endpoint 生成。
package com.hydro.filesvc;

import io.minio.MinioClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MinioConfig {

    @Bean
    // 创建 MinioClient，供文件写入服务复用。
    public MinioClient minioClient(
            @Value("${app.minio.endpoint}") String endpoint,
            @Value("${app.minio.access-key}") String accessKey,
            @Value("${app.minio.secret-key}") String secretKey
    ) {
        return MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
    }
}
