// file-service 的 gRPC 文件资产服务。
// 负责接收上传请求、写入 MinIO、保存元数据，并支持按 fileId 查询资产信息。
package com.hydro.filesvc.grpc;

import com.google.protobuf.ByteString;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hydro.filesvc.entity.FileAssetEntity;
import com.hydro.filesvc.mapper.FileAssetMapper;
import com.hydro.filesvc.storage.MinioObjectStorage;
import com.hydro.filesvc.storage.StoredObject;
import com.hydro.filesvc.support.FileAssetTypeResolver;
import com.hydro.filesvc.support.ObjectKeyFactory;
import com.hydro.grpc.filev1.FileReply;
import com.hydro.grpc.filev1.FileRpcServiceGrpc;
import com.hydro.grpc.filev1.GetFileRequest;
import com.hydro.grpc.filev1.UploadFileRequest;
import com.hydro.grpc.filev1.DownloadFileReply;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class FileGrpcService extends FileRpcServiceGrpc.FileRpcServiceImplBase {

    private final FileAssetMapper mapper;
    private final MinioObjectStorage objectStorage;
    private final ConcurrentMap<String, FileAssetEntity> memoryStore = new ConcurrentHashMap<>();

    // 注入元数据 Mapper 和 MinIO 存储封装。
    public FileGrpcService(
            FileAssetMapper mapper,
            MinioObjectStorage objectStorage
    ) {
        this.mapper = mapper;
        this.objectStorage = objectStorage;
    }

    @Override
    // 上传文件：先写 MinIO，再保存元数据，保证数据库里的 objectKey 指向真实对象。
    public void uploadFile(UploadFileRequest request, StreamObserver<FileReply> responseObserver) {
        if (request.getFileName() == null || request.getFileName().isBlank()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("file_name is required"));
            return;
        }
        if (request.getContent().isEmpty()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("content is required"));
            return;
        }

        try {
            String fileId = "file-" + UUID.randomUUID();
            String fileType = FileAssetTypeResolver.resolve(
                    request.getFileType(),
                    request.getFileName(),
                    request.getContentType()
            );
            String objectKey = ObjectKeyFactory.build(fileType, fileId, request.getFileName());
            StoredObject storedObject = objectStorage.putObject(
                    objectKey,
                    request.getContentType(),
                    request.getContent().toByteArray()
            );

            FileAssetEntity entity = buildEntity(request, fileId, fileType, storedObject);
            saveEntity(entity);

            responseObserver.onNext(toReply(entity, storedObject.downloadUrl()));
            responseObserver.onCompleted();
        } catch (IllegalArgumentException ex) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument(ex.getMessage()));
        } catch (Exception ex) {
            responseObserver.onError(GrpcServiceSupport.internal("file upload failed", ex));
        }
    }

    @Override
    // 按 fileId 查询文件资产元数据。
    public void getFile(GetFileRequest request, StreamObserver<FileReply> responseObserver) {
        FileAssetEntity entity = findEntity(request.getFileId());
        if (entity == null) {
            responseObserver.onError(GrpcServiceSupport.notFound("file not found: " + request.getFileId()));
            return;
        }

        responseObserver.onNext(toReply(entity, objectStorage.downloadUrlFor(entity.getObjectKey())));
        responseObserver.onCompleted();
    }

    @Override
    // 下载文件内容；主要给 agent-service 读取 scene_sample JSON 使用。
    public void downloadFile(GetFileRequest request, StreamObserver<DownloadFileReply> responseObserver) {
        FileAssetEntity entity = findEntity(request.getFileId());
        if (entity == null) {
            responseObserver.onError(GrpcServiceSupport.notFound("file not found: " + request.getFileId()));
            return;
        }
        try {
            byte[] content = objectStorage.getObject(entity.getObjectKey());
            responseObserver.onNext(DownloadFileReply.newBuilder()
                    .setFile(toReply(entity, objectStorage.downloadUrlFor(entity.getObjectKey())))
                    .setContent(ByteString.copyFrom(content))
                    .build());
            responseObserver.onCompleted();
        } catch (Exception ex) {
            responseObserver.onError(GrpcServiceSupport.internal("file download failed", ex));
        }
    }

    // 根据上传请求和存储结果构造元数据实体。
    private FileAssetEntity buildEntity(
            UploadFileRequest request,
            String fileId,
            String fileType,
            StoredObject storedObject
    ) {
        FileAssetEntity entity = new FileAssetEntity();
        entity.setFileId(fileId);
        entity.setFileName(request.getFileName());
        entity.setContentType(request.getContentType());
        entity.setObjectKey(storedObject.objectKey());
        entity.setFileType(fileType);
        entity.setChecksumSha256(storedObject.checksumSha256());
        entity.setSize(storedObject.size());
        entity.setCreatedAt(LocalDateTime.now());
        return entity;
    }

    // 从数据库或内存兜底缓存中查找文件资产实体。
    private FileAssetEntity findEntity(String fileId) {
        FileAssetEntity entity = null;
        try {
            entity = mapper.selectOne(
                    new LambdaQueryWrapper<FileAssetEntity>()
                            .eq(FileAssetEntity::getFileId, fileId)
            );
        } catch (Exception ignored) {
            entity = memoryStore.get(fileId);
        }
        if (entity == null) {
            entity = memoryStore.get(fileId);
        }
        return entity;
    }

    // 保存元数据；数据库不可用时放入内存兜底，保持查询链路可用。
    private void saveEntity(FileAssetEntity entity) {
        try {
            mapper.insert(entity);
        } catch (Exception ex) {
            memoryStore.put(entity.getFileId(), entity);
        }
    }

    // 将元数据实体转换成 gRPC 响应。
    private FileReply toReply(FileAssetEntity entity, String uploadedDownloadUrl) {
        String downloadUrl = uploadedDownloadUrl == null || uploadedDownloadUrl.isBlank()
                ? ""
                : uploadedDownloadUrl;
        return FileReply.newBuilder()
                .setFileId(entity.getFileId())
                .setFileName(nullSafe(entity.getFileName()))
                .setContentType(nullSafe(entity.getContentType()))
                .setSize(entity.getSize() == null ? 0 : entity.getSize())
                .setDownloadUrl(downloadUrl)
                .setObjectKey(nullSafe(entity.getObjectKey()))
                .setFileType(nullSafe(entity.getFileType()))
                .setChecksumSha256(nullSafe(entity.getChecksumSha256()))
                .build();
    }

    // 将 null 字符串安全转换为空字符串，避免 proto setter 收到 null。
    private String nullSafe(String value) {
        return value == null ? "" : value;
    }
}
