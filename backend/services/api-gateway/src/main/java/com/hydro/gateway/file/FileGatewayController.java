// 文件资产 HTTP 网关控制器。
// 前端通过 multipart 上传图像、点云等原始资产，网关转发给 file-service 保存到 MinIO。
package com.hydro.gateway.file;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.filev1.FileReply;
import com.hydro.grpc.filev1.FileRpcServiceGrpc;
import com.hydro.grpc.filev1.UploadFileRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/files")
public class FileGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String fileServiceName;
    private final long maxUploadBytes;
    private final int grpcMaxInboundMessageBytes;

    // 注入服务发现客户端、file-service 名称和上传大小配置。
    public FileGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.file-service-name:file-service}") String fileServiceName,
            @Value("${app.file-upload.max-bytes:104857600}") long maxUploadBytes,
            @Value("${app.file-upload.grpc-max-inbound-message-bytes:104857600}") int grpcMaxInboundMessageBytes
    ) {
        this.discoveryClient = discoveryClient;
        this.fileServiceName = fileServiceName;
        this.maxUploadBytes = maxUploadBytes;
        this.grpcMaxInboundMessageBytes = grpcMaxInboundMessageBytes;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    // 接收前端上传文件并转发 file-service；fileType 可传 image、point_cloud 等业务类型。
    public ResponseEntity<ApiResponse<Map<String, Object>>> uploadFile(
            @RequestParam("file") MultipartFile file,
            @RequestParam(value = "fileType", required = false) String fileType,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        UploadFileRequest request = FileUploadRequestFactory.build(file, fileType, maxUploadBytes);
        ManagedChannel channel = createFileChannel();
        try {
            FileRpcServiceGrpc.FileRpcServiceBlockingStub stub = FileRpcServiceGrpc.newBlockingStub(channel);
            FileReply reply = stub.uploadFile(request);
            return ResponseEntity.ok(ApiResponse.success(FileResponseMapper.toHttpData(reply), traceId(traceId)));
        } finally {
            channel.shutdown();
        }
    }

    @GetMapping("/{fileId}")
    // 查询文件资产元数据，便于前端上传后回显或后续 scene 样本装配引用。
    public ResponseEntity<ApiResponse<Map<String, Object>>> getFile(
            @PathVariable String fileId,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        ManagedChannel channel = createFileChannel();
        try {
            FileRpcServiceGrpc.FileRpcServiceBlockingStub stub = FileRpcServiceGrpc.newBlockingStub(channel);
            FileReply reply = stub.getFile(com.hydro.grpc.filev1.GetFileRequest.newBuilder()
                    .setFileId(fileId)
                    .build());
            return ResponseEntity.ok(ApiResponse.success(FileResponseMapper.toHttpData(reply), traceId(traceId)));
        } finally {
            channel.shutdown();
        }
    }

    // 创建到 file-service 的短生命周期 gRPC channel。
    private ManagedChannel createFileChannel() {
        ServiceInstance fileInstance = chooseServiceInstance(fileServiceName);
        return ManagedChannelBuilder.forAddress(fileInstance.getHost(), fileInstance.getPort())
                .usePlaintext()
                .maxInboundMessageSize(grpcMaxInboundMessageBytes)
                .build();
    }

    // 从服务发现结果中随机选择一个可用 file-service 实例。
    private ServiceInstance chooseServiceInstance(String serviceName) {
        List<ServiceInstance> instances = discoveryClient.getInstances(serviceName);
        if (instances == null || instances.isEmpty()) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, "No available instance for service: " + serviceName);
        }
        return instances.get(ThreadLocalRandom.current().nextInt(instances.size()));
    }

    // 读取链路 traceId；过滤器未执行时保留本地兜底。
    private String traceId(String traceId) {
        return traceId == null || traceId.isBlank()
                ? UUID.randomUUID().toString().replace("-", "")
                : traceId;
    }
}
