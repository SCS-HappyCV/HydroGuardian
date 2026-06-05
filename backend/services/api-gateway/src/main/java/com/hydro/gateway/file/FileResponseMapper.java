// 文件资产响应映射器。
// 将 file-service 的 gRPC 响应转换为前端稳定使用的 HTTP JSON 字段。
package com.hydro.gateway.file;

import com.hydro.grpc.filev1.FileReply;

import java.util.Map;

final class FileResponseMapper {

    // 工具类不需要实例化。
    private FileResponseMapper() {
    }

    // 转换文件资产响应。
    static Map<String, Object> toHttpData(FileReply reply) {
        return Map.of(
                "fileId", reply.getFileId(),
                "fileName", reply.getFileName(),
                "contentType", reply.getContentType(),
                "size", reply.getSize(),
                "downloadUrl", reply.getDownloadUrl(),
                "objectKey", reply.getObjectKey(),
                "fileType", reply.getFileType(),
                "checksumSha256", reply.getChecksumSha256()
        );
    }
}
