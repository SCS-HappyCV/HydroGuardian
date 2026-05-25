package com.hydro.gateway;

import com.hydro.grpc.agentv1.AgentRpcServiceGrpc;
import com.hydro.grpc.agentv1.ExecuteTaskReply;
import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/tasks")
public class TaskGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String agentServiceName;

    public TaskGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.agent-service-name:agent-service}") String agentServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.agentServiceName = agentServiceName;
    }

    @PostMapping("/execute")
    public ResponseEntity<ApiResponse<Map<String, Object>>> executeTask(
            @Valid @RequestBody ExecuteTaskRequest request,
            @RequestHeader(value = "X-Trace-Id", required = false) String traceId
    ) {
        String currentTraceId = (traceId == null || traceId.isBlank())
                ? UUID.randomUUID().toString().replace("-", "")
                : traceId;
        ServiceInstance agentInstance = chooseServiceInstance(agentServiceName);
        ManagedChannel channel = ManagedChannelBuilder.forAddress(agentInstance.getHost(), agentInstance.getPort())
                .usePlaintext()
                .build();
        try {
            AgentRpcServiceGrpc.AgentRpcServiceBlockingStub stub = AgentRpcServiceGrpc.newBlockingStub(channel);
            com.hydro.grpc.agentv1.ExecuteTaskRequest grpcReq = com.hydro.grpc.agentv1.ExecuteTaskRequest.newBuilder()
                    .setTaskText(request.taskText())
                    .setSceneId(request.sceneId())
                    .build();
            ExecuteTaskReply reply = stub.executeTask(grpcReq);

            return ResponseEntity.ok(ApiResponse.success(
                    Map.of(
                            "task", Map.of("taskText", reply.getTaskText(), "sceneId", reply.getSceneId()),
                            "parsed", Map.of("targetType", reply.getTargetType()),
                            "risk", Map.of("score", reply.getRiskScore(), "riskLevel", reply.getRiskLevel()),
                            "recommendation", Map.of("action", reply.getRecommendationAction()),
                            "case", Map.of("caseId", reply.getCaseId(), "status", reply.getCaseStatus())
                    ),
                    currentTraceId
            ));
        } finally {
            channel.shutdown();
        }
    }

    private ServiceInstance chooseServiceInstance(String serviceName) {
        List<ServiceInstance> instances = discoveryClient.getInstances(serviceName);
        if (instances == null || instances.isEmpty()) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, "No available instance for service: " + serviceName);
        }
        return instances.get(ThreadLocalRandom.current().nextInt(instances.size()));
    }

    public record ExecuteTaskRequest(
            @NotBlank(message = "taskText cannot be blank")
            String taskText,
            @NotBlank(message = "sceneId cannot be blank")
            String sceneId
    ) {
    }
}
