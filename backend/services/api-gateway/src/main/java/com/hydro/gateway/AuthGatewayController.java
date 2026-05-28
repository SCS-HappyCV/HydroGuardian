package com.hydro.gateway;

import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.gateway.dto.ApiResponse;
import com.hydro.grpc.casev1.AuthUser;
import com.hydro.grpc.casev1.CaseRpcServiceGrpc;
import com.hydro.grpc.casev1.LoginUserReply;
import com.hydro.grpc.casev1.RegisterUserReply;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthGatewayController {

    private final DiscoveryClient discoveryClient;
    private final String caseServiceName;
    private final String tokenSecret;

    public AuthGatewayController(
            DiscoveryClient discoveryClient,
            @Value("${app.case-service-name:case-service}") String caseServiceName,
            @Value("${app.auth-token-secret:hydroguardian-dev-secret}") String tokenSecret
    ) {
        this.discoveryClient = discoveryClient;
        this.caseServiceName = caseServiceName;
        this.tokenSecret = tokenSecret;
    }

    @PostMapping("/register")
    public ResponseEntity<ApiResponse<Map<String, Object>>> register(
            @Valid @RequestBody RegisterRequest request,
            HttpServletRequest servletRequest
    ) {
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            RegisterUserReply reply = stub.registerUser(
                    com.hydro.grpc.casev1.RegisterUserRequest.newBuilder()
                            .setName(request.name().trim())
                            .setEmail(request.email().trim())
                            .setPassword(request.password())
                            .setConfirmPassword(request.confirmPassword())
                            .setAgreeTerms(request.agreeTerms())
                            .build()
            );

            return ResponseEntity.ok(ApiResponse.success(
                    Map.of(
                            "userId", reply.getUserId(),
                            "email", reply.getEmail(),
                            "createdAt", reply.getCreatedAt()
                    ),
                    traceId(servletRequest)
            ));
        } finally {
            channel.shutdown();
        }
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<Map<String, Object>>> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest servletRequest
    ) {
        ManagedChannel channel = createCaseChannel();
        try {
            CaseRpcServiceGrpc.CaseRpcServiceBlockingStub stub = CaseRpcServiceGrpc.newBlockingStub(channel);
            LoginUserReply reply = stub.loginUser(
                    com.hydro.grpc.casev1.LoginUserRequest.newBuilder()
                            .setEmail(request.email().trim())
                            .setPassword(request.password())
                            .setRememberMe(Boolean.TRUE.equals(request.rememberMe()))
                            .build()
            );

            return ResponseEntity.ok(ApiResponse.success(
                    Map.of(
                            "token", createToken(reply.getTokenSubject(), reply.getExpiresIn()),
                            "tokenType", "Bearer",
                            "expiresIn", reply.getExpiresIn(),
                            "user", toUserMap(reply.getUser())
                    ),
                    traceId(servletRequest)
            ));
        } finally {
            channel.shutdown();
        }
    }

    private ManagedChannel createCaseChannel() {
        ServiceInstance instance = chooseServiceInstance(caseServiceName);
        return ManagedChannelBuilder.forAddress(instance.getHost(), instance.getPort())
                .usePlaintext()
                .build();
    }

    private ServiceInstance chooseServiceInstance(String serviceName) {
        List<ServiceInstance> instances = discoveryClient.getInstances(serviceName);
        if (instances == null || instances.isEmpty()) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, "No available instance for service: " + serviceName);
        }
        return instances.get(ThreadLocalRandom.current().nextInt(instances.size()));
    }

    private Map<String, Object> toUserMap(AuthUser user) {
        return Map.of(
                "id", user.getId(),
                "name", user.getName(),
                "email", user.getEmail(),
                "role", user.getRole(),
                "department", user.getDepartment(),
                "avatarUrl", user.getAvatarUrl()
        );
    }

    private String createToken(String subject, long expiresInSeconds) {
        long issuedAt = Instant.now().getEpochSecond();
        long expiresAt = issuedAt + expiresInSeconds;
        String tokenId = UUID.randomUUID().toString().replace("-", "");
        String header = base64Url("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        String payload = base64Url(json(Map.of(
                "sub", subject,
                "iat", issuedAt,
                "exp", expiresAt,
                "jti", tokenId
        )));
        return header + "." + payload + "." + sign(header + "." + payload);
    }

    private String sign(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(tokenSecret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to create auth token", ex);
        }
    }

    private String base64Url(String value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    private String json(Map<String, Object> values) {
        Map<String, Object> ordered = new LinkedHashMap<>(values);
        StringBuilder builder = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : ordered.entrySet()) {
            if (!first) {
                builder.append(',');
            }
            first = false;
            builder.append('"').append(entry.getKey()).append('"').append(':');
            Object value = entry.getValue();
            if (value instanceof Number || value instanceof Boolean) {
                builder.append(value);
            } else {
                builder.append('"').append(escapeJson(String.valueOf(value))).append('"');
            }
        }
        return builder.append('}').toString();
    }

    private String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private String traceId(HttpServletRequest request) {
        Object value = request.getAttribute("traceId");
        return value == null ? UUID.randomUUID().toString().replace("-", "") : value.toString();
    }

    public record LoginRequest(
            @NotBlank(message = "email cannot be blank")
            @Email(message = "email is invalid")
            String email,
            @NotBlank(message = "password cannot be blank")
            @Size(min = 6, message = "password must be at least 6 characters")
            String password,
            Boolean rememberMe
    ) {
    }

    public record RegisterRequest(
            @NotBlank(message = "name cannot be blank")
            @Size(min = 2, max = 20, message = "name length must be between 2 and 20")
            String name,
            @NotBlank(message = "email cannot be blank")
            @Email(message = "email is invalid")
            String email,
            @NotBlank(message = "password cannot be blank")
            @Size(min = 8, message = "password must be at least 8 characters")
            String password,
            @NotBlank(message = "confirmPassword cannot be blank")
            @Size(min = 8, message = "confirmPassword must be at least 8 characters")
            String confirmPassword,
            @AssertTrue(message = "agreeTerms must be true")
            boolean agreeTerms
    ) {
    }
}
