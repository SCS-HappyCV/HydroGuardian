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
    private volatile boolean running;
    private Server server;

    public GrpcServerLifecycle(
            FileGrpcService fileGrpcService,
            @Value("${grpc.server.port:9093}") int grpcPort
    ) {
        this.fileGrpcService = fileGrpcService;
        this.grpcPort = grpcPort;
    }

    @Override
    public void start() {
        try {
            server = ServerBuilder.forPort(grpcPort)
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
    public void stop() {
        if (server != null) {
            server.shutdown();
        }
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return Integer.MAX_VALUE;
    }
}

