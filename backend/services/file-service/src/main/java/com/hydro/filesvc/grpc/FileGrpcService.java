package com.hydro.filesvc.grpc;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hydro.filesvc.entity.FileAssetEntity;
import com.hydro.filesvc.mapper.FileAssetMapper;
import com.hydro.grpc.filev1.FileReply;
import com.hydro.grpc.filev1.FileRpcServiceGrpc;
import com.hydro.grpc.filev1.GetFileRequest;
import com.hydro.grpc.filev1.UploadFileRequest;
import io.grpc.stub.StreamObserver;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class FileGrpcService extends FileRpcServiceGrpc.FileRpcServiceImplBase {

    private final FileAssetMapper mapper;
    private final String minioEndpoint;
    private final String bucket;
    private final ConcurrentMap<String, FileAssetEntity> memoryStore = new ConcurrentHashMap<>();

    public FileGrpcService(
            FileAssetMapper mapper,
            @Value("${app.minio.endpoint}") String minioEndpoint,
            @Value("${app.minio.bucket}") String bucket
    ) {
        this.mapper = mapper;
        this.minioEndpoint = minioEndpoint;
        this.bucket = bucket;
    }

    @Override
    public void uploadFile(UploadFileRequest request, StreamObserver<FileReply> responseObserver) {
        if (request.getFileName() == null || request.getFileName().isBlank()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("file_name is required"));
            return;
        }

        String fileId = "file-" + UUID.randomUUID();
        String objectKey = fileId + "-" + request.getFileName();

        FileAssetEntity entity = new FileAssetEntity();
        entity.setFileId(fileId);
        entity.setFileName(request.getFileName());
        entity.setContentType(request.getContentType());
        entity.setObjectKey(objectKey);
        entity.setSize((long) request.getContent().size());

        try {
            mapper.insert(entity);
        } catch (Exception ex) {
            memoryStore.put(fileId, entity);
        }

        responseObserver.onNext(toReply(entity));
        responseObserver.onCompleted();
    }

    @Override
    public void getFile(GetFileRequest request, StreamObserver<FileReply> responseObserver) {
        FileAssetEntity entity = null;
        try {
            entity = mapper.selectOne(
                    new LambdaQueryWrapper<FileAssetEntity>()
                            .eq(FileAssetEntity::getFileId, request.getFileId())
            );
        } catch (Exception ignored) {
            entity = memoryStore.get(request.getFileId());
        }
        if (entity == null) {
            entity = memoryStore.get(request.getFileId());
        }
        if (entity == null) {
            responseObserver.onError(GrpcServiceSupport.notFound("file not found: " + request.getFileId()));
            return;
        }

        responseObserver.onNext(toReply(entity));
        responseObserver.onCompleted();
    }

    private FileReply toReply(FileAssetEntity entity) {
        String downloadUrl = minioEndpoint + "/" + bucket + "/" + entity.getObjectKey();
        return FileReply.newBuilder()
                .setFileId(entity.getFileId())
                .setFileName(nullSafe(entity.getFileName()))
                .setContentType(nullSafe(entity.getContentType()))
                .setSize(entity.getSize() == null ? 0 : entity.getSize())
                .setDownloadUrl(downloadUrl)
                .build();
    }

    private String nullSafe(String value) {
        return value == null ? "" : value;
    }
}
