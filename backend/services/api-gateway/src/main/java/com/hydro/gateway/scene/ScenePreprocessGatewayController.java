// 场景预处理 HTTP 网关控制器。
// 负责把前端预处理请求转发给 agent-service 内部的 PreprocessScene gRPC 方法。
package com.hydro.gateway.scene;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.agentv1.AgentRpcServiceGrpc;
import com.hydro.grpc.agentv1.PreprocessSceneReply;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
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
public class ScenePreprocessGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String agentServiceName;

    // 注入服务发现客户端和 agent-service 名称。
    public ScenePreprocessGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.agent-service-name:agent-service}") String agentServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.agentServiceName = agentServiceName;
    }

    @PostMapping("/preprocess")
    // 执行场景预处理，并返回生成的 SceneTensorSample fileId。
    public ResponseEntity<ApiResponse<Map<String, Object>>> preprocessScene(
            @Valid @RequestBody ScenePreprocessRequest request,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        ManagedChannel channel = createAgentChannel();
        try {
            AgentRpcServiceGrpc.AgentRpcServiceBlockingStub stub = AgentRpcServiceGrpc.newBlockingStub(channel);
            PreprocessSceneReply reply = stub.preprocessScene(buildGrpcRequest(request));
            return ResponseEntity.ok(ApiResponse.success(
                    ScenePreprocessResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    // 构建 agent-service gRPC 请求，统一处理可选整数字段的默认值。
    private com.hydro.grpc.agentv1.PreprocessSceneRequest buildGrpcRequest(ScenePreprocessRequest request) {
        return com.hydro.grpc.agentv1.PreprocessSceneRequest.newBuilder()
                .setSceneId(trimToEmpty(request.sceneId()))
                .setSampleId(trimToEmpty(request.sampleId()))
                .setImageFileId(trimToEmpty(request.imageFileId()))
                .setPointCloudFileId(trimToEmpty(request.pointCloudFileId()))
                .setPreImageFileId(trimToEmpty(request.preImageFileId()))
                .setPostImageFileId(trimToEmpty(request.postImageFileId()))
                .setPreprocessVersion(trimToEmpty(request.preprocessVersion()))
                .setImageSize(request.imageSize() == null ? 0 : request.imageSize())
                .setMaxPoints(request.maxPoints() == null ? 0 : request.maxPoints())
                .build();
    }

    // 创建到 agent-service 的短生命周期 gRPC channel。
    private ManagedChannel createAgentChannel() {
        ServiceInstance instance = chooseServiceInstance(agentServiceName);
        return ManagedChannelBuilder.forAddress(instance.getHost(), instance.getPort())
                .usePlaintext()
                .build();
    }

    // 从服务发现结果中随机选择一个可用 agent-service 实例。
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

    // 清理可选字符串字段，避免 proto setter 收到 null。
    private String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
