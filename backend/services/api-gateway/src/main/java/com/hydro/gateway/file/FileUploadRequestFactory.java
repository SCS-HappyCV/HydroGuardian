// 文件上传 gRPC 请求工厂。
// 负责把前端 multipart 文件转换为 file-service 的 UploadFileRequest，并做入口级大小校验。
package com.hydro.gateway.file;

import com.google.protobuf.ByteString;
import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.grpc.filev1.UploadFileRequest;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

final class FileUploadRequestFactory {

    // 工具类不需要实例化。
    private FileUploadRequestFactory() {
    }

    // 构建上传请求；文件内容在 MVP 阶段一次性读入内存，后续大文件可升级为分片或预签名直传。
    static UploadFileRequest build(MultipartFile file, String fileType, long maxBytes) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(ErrorCode.BAD_REQUEST, "file is required");
        }
        if (file.getSize() > maxBytes) {
            throw new ServiceException(ErrorCode.BAD_REQUEST, "file size exceeds limit: " + maxBytes + " bytes");
        }
        try {
            return UploadFileRequest.newBuilder()
                    .setFileName(resolveFileName(file))
                    .setContentType(resolveContentType(file))
                    .setContent(ByteString.copyFrom(file.getBytes()))
                    .setFileType(fileType == null ? "" : fileType)
                    .build();
        } catch (IOException exc) {
            throw new ServiceException(ErrorCode.BAD_REQUEST, "failed to read upload file");
        }
    }

    // 解析原始文件名；前端未提供时使用兜底名称。
    private static String resolveFileName(MultipartFile file) {
        String originalFilename = file.getOriginalFilename();
        return originalFilename == null || originalFilename.isBlank() ? "upload.bin" : originalFilename;
    }

    // 解析 MIME 类型；前端未提供时使用通用二进制类型。
    private static String resolveContentType(MultipartFile file) {
        String contentType = file.getContentType();
        return contentType == null || contentType.isBlank() ? "application/octet-stream" : contentType;
    }
}
