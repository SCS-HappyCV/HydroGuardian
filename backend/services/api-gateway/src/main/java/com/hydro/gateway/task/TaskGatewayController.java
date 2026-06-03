// 任务执行请求的 HTTP 控制器。
// 通过服务发现定位 agent-service，经 gRPC 转发请求，并在网关响应中返回智能体诊断字段。
package com.hydro.gateway.task;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.agentv1.AgentRpcServiceGrpc;
import com.hydro.grpc.agentv1.ExecuteTaskReply;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/tasks")
public class TaskGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String agentServiceName;

    // Spring 注入服务发现客户端和当前配置的 agent-service 名称。
    public TaskGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.agent-service-name:agent-service}") String agentServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.agentServiceName = agentServiceName;
    }

    @PostMapping("/execute")
    // 通过 agent-service 执行一条巡查任务，并将 gRPC 响应映射成 HTTP JSON。
    public ResponseEntity<ApiResponse<Map<String, Object>>> executeTask(
            @Valid @RequestBody ExecuteTaskRequest request,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        // 优先使用 TraceIdFilter 创建的 trace id；保留本地兜底，兼容测试或异常过滤器顺序。
        String currentTraceId = (traceId == null || traceId.isBlank())
                ? UUID.randomUUID().toString().replace("-", "")
                : traceId;
        ServiceInstance agentInstance = chooseServiceInstance(agentServiceName);

        // MVP 阶段使用短生命周期 channel 保持实现简单；后续流量增大时应改为连接池或 stub 托管。
        ManagedChannel channel = ManagedChannelBuilder.forAddress(agentInstance.getHost(), agentInstance.getPort())
                .usePlaintext()
                .build();
        try {
            AgentRpcServiceGrpc.AgentRpcServiceBlockingStub stub = AgentRpcServiceGrpc.newBlockingStub(channel);
            com.hydro.grpc.agentv1.ExecuteTaskRequest grpcReq =
                    com.hydro.grpc.agentv1.ExecuteTaskRequest.newBuilder()
                            .setTaskText(request.taskText())
                            .setSceneId(request.sceneId())
                            .setDebug(request.debugEnabled())
                            .build();
            ExecuteTaskReply reply = stub.executeTask(grpcReq);

            // HTTP 响应结构放到 mapper 中，避免新增智能体字段时让控制器变得臃肿。
            return ResponseEntity.ok(ApiResponse.success(
                    TaskResponseMapper.toHttpData(reply, request.debugEnabled()),
                    currentTraceId
            ));
        } finally {
            channel.shutdown();
        }
    }

    // 从 Nacos 服务发现结果中选择一个可用实例。
    private ServiceInstance chooseServiceInstance(String serviceName) {
        List<ServiceInstance> instances = discoveryClient.getInstances(serviceName);
        if (instances == null || instances.isEmpty()) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, "No available instance for service: " + serviceName);
        }
        return instances.get(ThreadLocalRandom.current().nextInt(instances.size()));
    }
}
