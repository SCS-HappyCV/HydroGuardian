package com.hydro.casehub.grpc;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hydro.casehub.entity.RiskCaseEntity;
import com.hydro.casehub.mapper.RiskCaseMapper;
import com.hydro.grpc.casev1.CaseReply;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.CreateCaseRequest;
import com.hydro.grpc.casev1.GetCaseRequest;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class CaseGrpcService extends CaseRpcServiceGrpc.CaseRpcServiceImplBase {

    private final RiskCaseMapper mapper;
    private final ConcurrentMap<String, RiskCaseEntity> memoryStore = new ConcurrentHashMap<>();

    public CaseGrpcService(RiskCaseMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void createCase(CreateCaseRequest request, StreamObserver<CaseReply> responseObserver) {
        if (request.getTitle() == null || request.getTitle().isBlank()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("title is required"));
            return;
        }
        RiskCaseEntity entity = buildEntity(request);
        try {
            mapper.insert(entity);
        } catch (Exception ex) {
            memoryStore.put(entity.getCaseId(), entity);
        }

        responseObserver.onNext(toReply(entity));
        responseObserver.onCompleted();
    }

    @Override
    public void getCase(GetCaseRequest request, StreamObserver<CaseReply> responseObserver) {
        RiskCaseEntity entity = null;
        try {
            entity = mapper.selectOne(
                    new LambdaQueryWrapper<RiskCaseEntity>()
                            .eq(RiskCaseEntity::getCaseId, request.getCaseId())
            );
        } catch (Exception ignored) {
            entity = memoryStore.get(request.getCaseId());
        }
        if (entity == null) {
            entity = memoryStore.get(request.getCaseId());
        }
        if (entity == null) {
            responseObserver.onError(GrpcServiceSupport.notFound("Case not found: " + request.getCaseId()));
            return;
        }
        responseObserver.onNext(toReply(entity));
        responseObserver.onCompleted();
    }

    private CaseReply toReply(RiskCaseEntity entity) {
        return CaseReply.newBuilder()
                .setCaseId(entity.getCaseId())
                .setTitle(nullSafe(entity.getTitle()))
                .setTaskText(nullSafe(entity.getTaskText()))
                .setSceneId(nullSafe(entity.getSceneId()))
                .setStatus(nullSafe(entity.getStatus()))
                .setRiskLevel(nullSafe(entity.getRiskLevel()))
                .setAssignee(nullSafe(entity.getAssignee()))
                .setTags(nullSafe(entity.getTags()))
                .setCreatedAt(entity.getCreatedAt() == null ? "" : entity.getCreatedAt().toString())
                .build();
    }

    private RiskCaseEntity buildEntity(CreateCaseRequest request) {
        RiskCaseEntity entity = new RiskCaseEntity();
        entity.setCaseId("case-" + UUID.randomUUID());
        entity.setTitle(request.getTitle());
        entity.setTaskText(request.getTaskText());
        entity.setSceneId(request.getSceneId());
        entity.setStatus("OPEN");
        entity.setRiskLevel(request.getRiskLevel().isBlank() ? "MEDIUM" : request.getRiskLevel());
        entity.setAssignee(request.getAssignee());
        entity.setTags(request.getTags().isBlank() ? "[]" : request.getTags());
        entity.setCreatedAt(LocalDateTime.now());
        return entity;
    }

    private String nullSafe(String value) {
        return value == null ? "" : value;
    }
}
