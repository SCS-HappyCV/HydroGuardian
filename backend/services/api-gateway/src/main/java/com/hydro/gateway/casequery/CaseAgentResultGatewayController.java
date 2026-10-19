// 风险 case 智能体快照 HTTP 网关控制器。
// 负责把前端的 case agent-result 查询转发到 case-service 的 GetCase gRPC 接口。
package com.hydro.gateway.casequery;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.casev1.CaseReply;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.GetCaseRequest;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/cases")
public class CaseAgentResultGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String caseServiceName;

    // 注入服务发现客户端和 case-service 名称。
    public CaseAgentResultGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.case-service-name:case-service}") String caseServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.caseServiceName = caseServiceName;
    }

    @GetMapping("/{caseId}/agent-result")
    // 查询指定 case 的完整智能体执行快照，供风险工作台展示 EvidencePack、RiskCard 和后续可视化数据。
    public ResponseEntity<ApiResponse<Map<String, Object>>> getCaseAgentResult(
            @PathVariable String caseId,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateNotBlank(caseId, "caseId");
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            CaseReply reply = stub.getCase(GetCaseRequest.newBuilder()
                    .setCaseId(caseId.trim())
                    .build());
            return ResponseEntity.ok(ApiResponse.success(
                    CaseAgentResultResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
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

    // 校验路径变量不为空。
    private void validateNotBlank(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new ServiceException(ErrorCode.BAD_REQUEST, fieldName + " is required");
        }
    }

    // 读取链路 traceId；过滤器未执行时保留本地兜底。
    private String traceId(String traceId) {
        return traceId == null || traceId.isBlank()
                ? UUID.randomUUID().toString().replace("-", "")
                : traceId;
    }
}
