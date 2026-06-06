// 工单 HTTP 网关控制器。
// 负责把前端工单查询和状态更新请求转发到 case-service 的 gRPC 工单接口。
package com.hydro.gateway.workorder;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.ListCaseWorkOrdersReply;
import com.hydro.grpc.casev1.WorkOrderReply;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1")
public class WorkOrderGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String caseServiceName;

    // 注入服务发现客户端和 case-service 名称。
    public WorkOrderGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.case-service-name:case-service}") String caseServiceName
    ) {
        this.discoveryClient = discoveryClient;
        this.caseServiceName = caseServiceName;
    }

    @GetMapping("/work-orders/{workOrderId}")
    // 查询单个工单详情。
    public ResponseEntity<ApiResponse<Map<String, Object>>> getWorkOrder(
            @PathVariable String workOrderId,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateNotBlank(workOrderId, "workOrderId");
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            WorkOrderReply reply = stub.getWorkOrder(
                    com.hydro.grpc.casev1.GetWorkOrderRequest.newBuilder()
                            .setWorkOrderId(workOrderId.trim())
                            .build()
            );
            return ResponseEntity.ok(ApiResponse.success(
                    WorkOrderResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    @GetMapping("/cases/{caseId}/work-orders")
    // 查询指定 case 下的所有工单。
    public ResponseEntity<ApiResponse<Map<String, Object>>> listCaseWorkOrders(
            @PathVariable String caseId,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateNotBlank(caseId, "caseId");
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            ListCaseWorkOrdersReply reply = stub.listCaseWorkOrders(
                    com.hydro.grpc.casev1.ListCaseWorkOrdersRequest.newBuilder()
                            .setCaseId(caseId.trim())
                            .build()
            );
            return ResponseEntity.ok(ApiResponse.success(
                    Map.of("workOrders", reply.getWorkOrdersList().stream()
                            .map(WorkOrderResponseMapper::toHttpData)
                            .toList()),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    @PatchMapping("/work-orders/{workOrderId}/status")
    // 更新工单状态和可选负责人、关闭说明。
    public ResponseEntity<ApiResponse<Map<String, Object>>> updateWorkOrderStatus(
            @PathVariable String workOrderId,
            @Valid @RequestBody com.hydro.gateway.workorder.UpdateWorkOrderStatusRequest request,
            @RequestAttribute(value = "traceId", required = false) String traceId
    ) {
        validateNotBlank(workOrderId, "workOrderId");
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            WorkOrderReply reply = stub.updateWorkOrderStatus(buildGrpcRequest(workOrderId, request));
            return ResponseEntity.ok(ApiResponse.success(
                    WorkOrderResponseMapper.toHttpData(reply),
                    traceId(traceId)
            ));
        } finally {
            channel.shutdown();
        }
    }

    // 构建更新状态的 gRPC 请求。
    private com.hydro.grpc.casev1.UpdateWorkOrderStatusRequest buildGrpcRequest(
            String workOrderId,
            com.hydro.gateway.workorder.UpdateWorkOrderStatusRequest request
    ) {
        return com.hydro.grpc.casev1.UpdateWorkOrderStatusRequest.newBuilder()
                .setWorkOrderId(workOrderId.trim())
                .setStatus(trimToEmpty(request.status()))
                .setAssignee(trimToEmpty(request.assignee()))
                .setClosureNote(trimToEmpty(request.closureNote()))
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

    // 清理可选字符串字段，避免 proto setter 收到 null。
    private String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
