package com.hydro.casehub.grpc;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.hydro.casehub.auth.PasswordHasher;
import com.hydro.casehub.entity.AppUserEntity;
import com.hydro.casehub.entity.RiskCaseEntity;
import com.hydro.casehub.mapper.AppUserMapper;
import com.hydro.casehub.mapper.RiskCaseMapper;
import com.hydro.grpc.casev1.AuthUser;
import com.hydro.grpc.casev1.CaseReply;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.CreateCaseRequest;
import com.hydro.grpc.casev1.GetCaseRequest;
import com.hydro.grpc.casev1.LoginUserReply;
import com.hydro.grpc.casev1.LoginUserRequest;
import com.hydro.grpc.casev1.RegisterUserReply;
import com.hydro.grpc.casev1.RegisterUserRequest;
import io.grpc.stub.StreamObserver;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class CaseGrpcService extends CaseRpcServiceGrpc.CaseRpcServiceImplBase {

    private final RiskCaseMapper mapper;
    private final AppUserMapper appUserMapper;
    private final PasswordHasher passwordHasher;
    private final ConcurrentMap<String, RiskCaseEntity> memoryStore = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, AppUserEntity> userMemoryStore = new ConcurrentHashMap<>();

    public CaseGrpcService(RiskCaseMapper mapper, AppUserMapper appUserMapper, PasswordHasher passwordHasher) {
        this.mapper = mapper;
        this.appUserMapper = appUserMapper;
        this.passwordHasher = passwordHasher;
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

    @Override
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

    private String normalizeEmail(String email) {
        return email == null ? "" : email.trim().toLowerCase(Locale.ROOT);
    }

    private boolean isValidEmail(String email) {
        return email != null && email.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");
    }

    private boolean isStrongPassword(String password) {
        return password != null
                && password.length() >= 8
                && password.chars().anyMatch(Character::isUpperCase)
                && password.chars().anyMatch(Character::isDigit);
    }

    private String nullSafe(String value) {
        return value == null ? "" : value;
    }
}
