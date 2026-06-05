// file-service gRPC 服务生命周期管理。
// Spring Boot 负责 HTTP/Actuator，业务 gRPC 服务由这里单独启动。
package com.hydro.filesvc.grpc;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class GrpcServerLifecycle implements SmartLifecycle {

    private final FileGrpcService fileGrpcService;
    private final int grpcPort;
    private final int maxInboundMessageBytes;
    private volatile boolean running;
    private Server server;

    // 注入 gRPC 服务实例、监听端口和最大入站消息大小。
    public GrpcServerLifecycle(
            FileGrpcService fileGrpcService,
            @Value("${grpc.server.port:9093}") int grpcPort,
            @Value("${grpc.server.max-inbound-message-bytes:104857600}") int maxInboundMessageBytes
    ) {
        this.fileGrpcService = fileGrpcService;
        this.grpcPort = grpcPort;
        this.maxInboundMessageBytes = maxInboundMessageBytes;
    }

    @Override
    // 启动 gRPC server，并放大消息限制以支持点云和大图上传。
    public void start() {
        try {
            server = ServerBuilder.forPort(grpcPort)
                    .maxInboundMessageSize(maxInboundMessageBytes)
                    .addService(fileGrpcService)
                    .build()
                    .start();
            running = true;
            System.out.println("file-service gRPC started on port " + grpcPort);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to start file-service gRPC server", e);
        }
    }

    @Override
    // 停止 gRPC server，供 Spring 生命周期回收。
    public void stop() {
        if (server != null) {
            server.shutdown();
        }
        running = false;
    }

    @Override
    // 返回当前 gRPC server 是否正在运行。
    public boolean isRunning() {
        return running;
    }

    @Override
    // 尽量晚启动，确保 Spring Bean 和配置都已准备好。
    public int getPhase() {
        return Integer.MAX_VALUE;
    }
}
