// case-service 的 gRPC 服务实现。
// 这里负责 case 主表、agent 执行快照表、场景资产清单和用户鉴权请求的落库与兜底缓存。
package com.hydro.casehub.grpc;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hydro.casehub.auth.PasswordHasher;
import com.hydro.casehub.entity.AppUserEntity;
import com.hydro.casehub.entity.CaseAgentResultEntity;
import com.hydro.casehub.entity.RiskCaseEntity;
import com.hydro.casehub.entity.SceneAssetManifestEntity;
import com.hydro.casehub.mapper.AppUserMapper;
import com.hydro.casehub.mapper.CaseAgentResultMapper;
import com.hydro.casehub.mapper.RiskCaseMapper;
import com.hydro.casehub.mapper.SceneAssetManifestMapper;
import com.hydro.grpc.casev1.AuthUser;
import com.hydro.grpc.casev1.CaseReply;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.CreateCaseRequest;
import com.hydro.grpc.casev1.CreateSceneManifestRequest;
import com.hydro.grpc.casev1.GetCaseRequest;
import com.hydro.grpc.casev1.GetSceneManifestRequest;
import com.hydro.grpc.casev1.LoginUserReply;
import com.hydro.grpc.casev1.LoginUserRequest;
import com.hydro.grpc.casev1.RegisterUserReply;
import com.hydro.grpc.casev1.RegisterUserRequest;
import com.hydro.grpc.casev1.SceneManifestReply;
import io.grpc.stub.StreamObserver;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
// 组合 case、agent_result、场景清单和用户四类能力的 gRPC 服务。
public class CaseGrpcService extends CaseRpcServiceGrpc.CaseRpcServiceImplBase {

    private final RiskCaseMapper mapper;
    private final CaseAgentResultMapper agentResultMapper;
    private final SceneAssetManifestMapper sceneAssetManifestMapper;
    private final AppUserMapper appUserMapper;
    private final PasswordHasher passwordHasher;
    private final ConcurrentMap<String, RiskCaseEntity> memoryStore = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, CaseAgentResultEntity> agentResultMemoryStore = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, SceneAssetManifestEntity> sceneManifestMemoryStore = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, AppUserEntity> userMemoryStore = new ConcurrentHashMap<>();

    // 注入 case 主表、agent 结果表、场景清单表、用户表和密码工具。
    public CaseGrpcService(
            RiskCaseMapper mapper,
            CaseAgentResultMapper agentResultMapper,
            SceneAssetManifestMapper sceneAssetManifestMapper,
            AppUserMapper appUserMapper,
            PasswordHasher passwordHasher
    ) {
        this.mapper = mapper;
        this.agentResultMapper = agentResultMapper;
        this.sceneAssetManifestMapper = sceneAssetManifestMapper;
        this.appUserMapper = appUserMapper;
        this.passwordHasher = passwordHasher;
    }

    @Override
    // 创建风险 case，并在 agent_result_json 不为空时同步保存完整智能体快照。
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

        persistAgentResult(entity.getCaseId(), request.getAgentResultJson());

        responseObserver.onNext(toReply(entity, loadAgentResultJson(entity.getCaseId())));
        responseObserver.onCompleted();
    }

    @Override
    // 查询风险 case，并附带对应的 agent 执行快照 JSON。
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
        responseObserver.onNext(toReply(entity, loadAgentResultJson(entity.getCaseId())));
        responseObserver.onCompleted();
    }

    @Override
    // 创建或更新场景资产清单，供 agent-service 按 scene_id 找到真实样本资产。
    public void createSceneManifest(
            CreateSceneManifestRequest request,
            StreamObserver<SceneManifestReply> responseObserver
    ) {
        String validationError = validateCreateSceneManifest(request);
        if (!validationError.isBlank()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument(validationError));
            return;
        }

        SceneAssetManifestEntity entity = buildSceneManifestEntity(request);
        upsertSceneManifest(entity);

        responseObserver.onNext(toSceneManifestReply(entity));
        responseObserver.onCompleted();
    }

    @Override
    // 查询场景资产清单；未命中时明确返回 NOT_FOUND，方便 agent-service 回退本地清单。
    public void getSceneManifest(
            GetSceneManifestRequest request,
            StreamObserver<SceneManifestReply> responseObserver
    ) {
        String sceneId = trimToEmpty(request.getSceneId());
        if (sceneId.isBlank()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("scene_id is required"));
            return;
        }

        SceneAssetManifestEntity entity = findSceneManifestBySceneId(sceneId);
        if (entity == null) {
            responseObserver.onError(GrpcServiceSupport.notFound("Scene manifest not found: " + sceneId));
            return;
        }

        responseObserver.onNext(toSceneManifestReply(entity));
        responseObserver.onCompleted();
    }

    @Override
    // 注册新用户，并在数据库不可用时保留内存兜底。
    public void registerUser(RegisterUserRequest request, StreamObserver<RegisterUserReply> responseObserver) {
        String name = request.getName().trim();
        String email = normalizeEmail(request.getEmail());
        String password = request.getPassword();
        String confirmPassword = request.getConfirmPassword();

        if (name.length() < 2 || name.length() > 20) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("name length must be between 2 and 20"));
            return;
        }
        if (!isValidEmail(email)) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("email is invalid"));
            return;
        }
        if (!request.getAgreeTerms()) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("agreeTerms is required"));
            return;
        }
        if (!password.equals(confirmPassword)) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("password and confirmPassword do not match"));
            return;
        }
        if (!isStrongPassword(password)) {
            responseObserver.onError(GrpcServiceSupport.invalidArgument("password must be at least 8 characters and contain uppercase letters and digits"));
            return;
        }
        if (findUserByEmail(email) != null) {
            responseObserver.onError(GrpcServiceSupport.alreadyExists("email already registered"));
            return;
        }

        AppUserEntity user = new AppUserEntity();
        LocalDateTime now = LocalDateTime.now();
        user.setUserId("user-" + UUID.randomUUID());
        user.setName(name);
        user.setEmail(email);
        user.setPasswordHash(passwordHasher.hash(password));
        user.setRoleId("role-operator");
        user.setRoleCode("operator");
        user.setDepartment("");
        user.setStatus("active");
        user.setAvatarUrl("");
        user.setCreatedAt(now);
        user.setUpdatedAt(now);

        try {
            appUserMapper.insert(user);
        } catch (DuplicateKeyException ex) {
            responseObserver.onError(GrpcServiceSupport.alreadyExists("email already registered"));
            return;
        } catch (Exception ex) {
            userMemoryStore.put(email, user);
        }

        responseObserver.onNext(RegisterUserReply.newBuilder()
                .setUserId(user.getUserId())
                .setEmail(user.getEmail())
                .setCreatedAt(now.toString())
                .build());
        responseObserver.onCompleted();
    }

    @Override
    // 校验用户登录凭据，并返回网关可签发 token 的用户摘要。
    public void loginUser(LoginUserRequest request, StreamObserver<LoginUserReply> responseObserver) {
        String email = normalizeEmail(request.getEmail());
        if (!isValidEmail(email) || request.getPassword().isBlank()) {
            responseObserver.onError(GrpcServiceSupport.unauthenticated("email or password is incorrect"));
            return;
        }

        AppUserEntity user = findUserByEmail(email);
        if (user == null || !passwordHasher.matches(request.getPassword(), user.getPasswordHash())) {
            responseObserver.onError(GrpcServiceSupport.unauthenticated("email or password is incorrect"));
            return;
        }
        if (!"active".equalsIgnoreCase(nullSafe(user.getStatus()))) {
            responseObserver.onError(GrpcServiceSupport.permissionDenied("user is disabled"));
            return;
        }

        user.setLastLoginAt(LocalDateTime.now());
        try {
            appUserMapper.updateById(user);
        } catch (Exception ignored) {
            userMemoryStore.put(email, user);
        }

        responseObserver.onNext(LoginUserReply.newBuilder()
                .setTokenSubject(user.getUserId())
                .setExpiresIn(request.getRememberMe() ? 604800 : 7200)
                .setUser(toAuthUser(user))
                .build());
        responseObserver.onCompleted();
    }

    // 将数据库实体转换为 gRPC 响应。
    private CaseReply toReply(RiskCaseEntity entity, String agentResultJson) {
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
                .setAgentResultJson(nullSafe(agentResultJson))
                .build();
    }

    // 根据 CreateCaseRequest 构建 risk_case 主表实体。
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

    // 保存 agent 执行快照；数据库失败时进入内存兜底，保持原有容错策略。
    private void persistAgentResult(String caseId, String agentResultJson) {
        if (agentResultJson == null || agentResultJson.isBlank()) {
            return;
        }
        CaseAgentResultEntity entity = buildAgentResultEntity(caseId, agentResultJson);
        try {
            agentResultMapper.insert(entity);
        } catch (Exception ignored) {
            agentResultMemoryStore.put(caseId, entity);
        }
    }

    // 构建 case_agent_result 表实体。
    private CaseAgentResultEntity buildAgentResultEntity(String caseId, String agentResultJson) {
        LocalDateTime now = LocalDateTime.now();
        CaseAgentResultEntity entity = new CaseAgentResultEntity();
        entity.setCaseId(caseId);
        entity.setAgentResultJson(agentResultJson);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    // 读取 agent 执行快照 JSON；数据库不可用时回退到内存缓存。
    private String loadAgentResultJson(String caseId) {
        try {
            CaseAgentResultEntity entity = agentResultMapper.selectOne(
                    new LambdaQueryWrapper<CaseAgentResultEntity>()
                            .eq(CaseAgentResultEntity::getCaseId, caseId)
            );
            if (entity != null) {
                return entity.getAgentResultJson();
            }
        } catch (Exception ignored) {
            CaseAgentResultEntity entity = agentResultMemoryStore.get(caseId);
            return entity == null ? "" : entity.getAgentResultJson();
        }
        CaseAgentResultEntity entity = agentResultMemoryStore.get(caseId);
        return entity == null ? "" : entity.getAgentResultJson();
    }

    // 校验场景清单创建请求，避免写入不可用的资产索引。
    private String validateCreateSceneManifest(CreateSceneManifestRequest request) {
        if (trimToEmpty(request.getSceneId()).isBlank()) {
            return "scene_id is required";
        }
        if (trimToEmpty(request.getSceneSampleFileId()).isBlank()) {
            return "scene_sample_file_id is required";
        }
        return "";
    }

    // 根据 gRPC 请求构建 scene_asset_manifest 表实体。
    private SceneAssetManifestEntity buildSceneManifestEntity(CreateSceneManifestRequest request) {
        LocalDateTime now = LocalDateTime.now();
        String sceneId = trimToEmpty(request.getSceneId());
        String sampleId = trimToEmpty(request.getSampleId());

        SceneAssetManifestEntity entity = new SceneAssetManifestEntity();
        entity.setSceneId(sceneId);
        entity.setSampleId(sampleId.isBlank() ? sceneId : sampleId);
        entity.setSceneSampleFileId(trimToEmpty(request.getSceneSampleFileId()));
        entity.setImageFileId(trimToEmpty(request.getImageFileId()));
        entity.setPointCloudFileId(trimToEmpty(request.getPointCloudFileId()));
        entity.setPreImageFileId(trimToEmpty(request.getPreImageFileId()));
        entity.setPostImageFileId(trimToEmpty(request.getPostImageFileId()));
        entity.setPreprocessVersion(trimToEmpty(request.getPreprocessVersion()));
        entity.setChecksumSha256(trimToEmpty(request.getChecksumSha256()));
        entity.setSchemaVersion(defaultSceneManifestSchemaVersion(request.getSchemaVersion()));
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    // 插入或更新清单；数据库不可用时写入内存缓存，保持 MVP 联调可用。
    private void upsertSceneManifest(SceneAssetManifestEntity entity) {
        try {
            SceneAssetManifestEntity existing = sceneAssetManifestMapper.selectOne(
                    new LambdaQueryWrapper<SceneAssetManifestEntity>()
                            .eq(SceneAssetManifestEntity::getSceneId, entity.getSceneId())
            );
            if (existing != null) {
                entity.setId(existing.getId());
                entity.setCreatedAt(existing.getCreatedAt());
                sceneAssetManifestMapper.updateById(entity);
            } else {
                sceneAssetManifestMapper.insert(entity);
            }
            sceneManifestMemoryStore.put(entity.getSceneId(), entity);
        } catch (DuplicateKeyException ex) {
            retrySceneManifestUpdate(entity);
        } catch (Exception ignored) {
            sceneManifestMemoryStore.put(entity.getSceneId(), entity);
        }
    }

    // 处理并发注册同一个 scene_id 时的唯一键冲突，尽量转换成更新语义。
    private void retrySceneManifestUpdate(SceneAssetManifestEntity entity) {
        try {
            SceneAssetManifestEntity existing = sceneAssetManifestMapper.selectOne(
                    new LambdaQueryWrapper<SceneAssetManifestEntity>()
                            .eq(SceneAssetManifestEntity::getSceneId, entity.getSceneId())
            );
            if (existing == null) {
                sceneManifestMemoryStore.put(entity.getSceneId(), entity);
                return;
            }
            entity.setId(existing.getId());
            entity.setCreatedAt(existing.getCreatedAt());
            sceneAssetManifestMapper.updateById(entity);
            sceneManifestMemoryStore.put(entity.getSceneId(), entity);
        } catch (Exception ignored) {
            sceneManifestMemoryStore.put(entity.getSceneId(), entity);
        }
    }

    // 根据 scene_id 读取清单；数据库查询失败或未命中时回退内存缓存。
    private SceneAssetManifestEntity findSceneManifestBySceneId(String sceneId) {
        try {
            SceneAssetManifestEntity entity = sceneAssetManifestMapper.selectOne(
                    new LambdaQueryWrapper<SceneAssetManifestEntity>()
                            .eq(SceneAssetManifestEntity::getSceneId, sceneId)
            );
            if (entity != null) {
                return entity;
            }
        } catch (Exception ignored) {
            return sceneManifestMemoryStore.get(sceneId);
        }
        return sceneManifestMemoryStore.get(sceneId);
    }

    // 将场景清单实体转换为 gRPC 响应。
    private SceneManifestReply toSceneManifestReply(SceneAssetManifestEntity entity) {
        return SceneManifestReply.newBuilder()
                .setSceneId(nullSafe(entity.getSceneId()))
                .setSampleId(nullSafe(entity.getSampleId()))
                .setSceneSampleFileId(nullSafe(entity.getSceneSampleFileId()))
                .setImageFileId(nullSafe(entity.getImageFileId()))
                .setPointCloudFileId(nullSafe(entity.getPointCloudFileId()))
                .setPreImageFileId(nullSafe(entity.getPreImageFileId()))
                .setPostImageFileId(nullSafe(entity.getPostImageFileId()))
                .setPreprocessVersion(nullSafe(entity.getPreprocessVersion()))
                .setChecksumSha256(nullSafe(entity.getChecksumSha256()))
                .setCreatedAt(entity.getCreatedAt() == null ? "" : entity.getCreatedAt().toString())
                .setUpdatedAt(entity.getUpdatedAt() == null ? "" : entity.getUpdatedAt().toString())
                .setSchemaVersion(defaultSceneManifestSchemaVersion(entity.getSchemaVersion()))
                .build();
    }

    // 缺省清单版本，保证旧请求也能被 agent-service 正常归一化。
    private String defaultSceneManifestSchemaVersion(String schemaVersion) {
        String normalized = trimToEmpty(schemaVersion);
        return normalized.isBlank() ? "scene_asset_manifest.v1" : normalized;
    }

    // 根据邮箱查找用户；数据库失败时回退到内存缓存。
    private AppUserEntity findUserByEmail(String email) {
        try {
            AppUserEntity user = appUserMapper.selectOne(
                    new LambdaQueryWrapper<AppUserEntity>()
                            .eq(AppUserEntity::getEmail, email)
            );
            if (user != null) {
                return user;
            }
        } catch (Exception ignored) {
            return userMemoryStore.get(email);
        }
        return userMemoryStore.get(email);
    }

    // 将数据库用户实体转换为鉴权响应对象。
    private AuthUser toAuthUser(AppUserEntity user) {
        return AuthUser.newBuilder()
                .setId(nullSafe(user.getUserId()))
                .setName(nullSafe(user.getName()))
                .setEmail(nullSafe(user.getEmail()))
                .setRole(nullSafe(user.getRoleCode()))
                .setDepartment(nullSafe(user.getDepartment()))
                .setAvatarUrl(nullSafe(user.getAvatarUrl()))
                .build();
    }

    // 归一化邮箱，避免大小写和首尾空格导致重复账户。
    private String normalizeEmail(String email) {
        return email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    }

    // 校验邮箱格式。
    private boolean isValidEmail(String email) {
        return email != null && email.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    }

    // 校验密码强度。
    private boolean isStrongPassword(String password) {
        return password != null
                && password.length() >= 8
                && password.chars().anyMatch(Character::isUpperCase)
                && password.chars().anyMatch(Character::isDigit);
    }

    // 清理字符串首尾空白，避免把空格写进业务主键。
    private String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }

    // 将 null 字符串安全转换为空字符串，避免 proto setter 收到 null。
    private String nullSafe(String value) {
        return value == null ? "" : value;
    }
}
