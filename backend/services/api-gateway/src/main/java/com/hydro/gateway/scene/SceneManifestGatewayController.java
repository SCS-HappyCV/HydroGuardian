// 场景资产清单 HTTP 网关控制器。
// 负责把前端注册/查询清单请求转发给 case-service，让 agent-service 可按 sceneId 找到真实样本资产。
package com.hydro.gateway.scene;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.CreateSceneManifestRequest;
import com.hydro.grpc.casev1.SceneManifestReply;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/scenes")
public class SceneManifestGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String caseServiceName;

    // 注入服务发现客户端和 case-service 名称。
    public SceneManifestGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.case-service-name:case-service}") String caseServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.caseServiceName = caseServiceName;
    }

    @PostMapping("/{sceneId}/manifest")
    // 注册或更新指定 sceneId 的资产清单。
    public ResponseEntity<ApiResponse<Map<String, Object>>> upsertManifest(
            @PathVariable String sceneId,
            @Valid @RequestBody SceneManifestRequest request,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateSceneId(sceneId);
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            SceneManifestReply reply = stub.createSceneManifest(buildCreateRequest(sceneId, request));
            return ResponseEntity.ok(ApiResponse.success(
                    SceneManifestResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    @GetMapping("/{sceneId}/manifest")
    // 查询指定 sceneId 的资产清单。
    public ResponseEntity<ApiResponse<Map<String, Object>>> getManifest(
            @PathVariable String sceneId,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateSceneId(sceneId);
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            SceneManifestReply reply = stub.getSceneManifest(
                    com.hydro.grpc.casev1.GetSceneManifestRequest.newBuilder()
                            .setSceneId(sceneId.trim())
                            .build()
            );
            return ResponseEntity.ok(ApiResponse.success(
                    SceneManifestResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    // 构建注册清单的 gRPC 请求，path 中的 sceneId 是唯一可信来源。
    private CreateSceneManifestRequest buildCreateRequest(String sceneId, SceneManifestRequest request) {
        return CreateSceneManifestRequest.newBuilder()
                .setSceneId(sceneId.trim())
                .setSampleId(trimToEmpty(request.sampleId()))
                .setSceneSampleFileId(trimToEmpty(request.sceneSampleFileId()))
                .setImageFileId(trimToEmpty(request.imageFileId()))
                .setPointCloudFileId(trimToEmpty(request.pointCloudFileId()))
                .setPreImageFileId(trimToEmpty(request.preImageFileId()))
                .setPostImageFileId(trimToEmpty(request.postImageFileId()))
                .setPreprocessVersion(trimToEmpty(request.preprocessVersion()))
                .setChecksumSha256(trimToEmpty(request.checksumSha256()))
                .setSchemaVersion(trimToEmpty(request.schemaVersion()))
                .build();
    }

    // 创建到 case-service 的短生命周期 gRPC channel。
    private ManagedChannel createCaseChannel() {
        ServiceInstance instance = chooseServiceInstance(caseServiceName);
        return ManagedChannelBuilder.forAddress(instance.getHost(), instance.getPort())
                .usePlaintext()
                .build();
    }

    // 从服务发现结果中随机选择一个可用 case-service 实例。
    private ServiceInstance chooseServiceInstance(String serviceName) {
        List<ServiceInstance> instances = discoveryClient.getInstances(serviceName);
        if (instances == null || instances.isEmpty()) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, "No available instance for service: " + serviceName);
        }
        return instances.get(ThreadLocalRandom.current().nextInt(instances.size()));
    }

    // 校验 URL 中的 sceneId，避免空主键进入 case-service。
    private void validateSceneId(String sceneId) {
        if (sceneId == null || sceneId.isBlank()) {
            throw new ServiceException(ErrorCode.BAD_REQUEST, "sceneId is required");
        }
    }

    // 读取链路 traceId；过滤器未执行时保留本地兜底。
    private String traceId(String traceId) {
        return traceId == null || traceId.isBlank()
                ? UUID.randomUUID().toString().replace("-", "")
                : traceId;
    }

    // 清理可选字符串字段，避免 proto setter 收到 null。
    private String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
