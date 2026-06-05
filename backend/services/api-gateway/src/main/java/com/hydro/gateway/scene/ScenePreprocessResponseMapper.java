// 场景预处理响应映射器。
// 将 agent-service 的 gRPC 响应转换为前端稳定使用的 HTTP JSON 字段。
package com.hydro.gateway.scene;

import com.hydro.grpc.agentv1.PreprocessSceneReply;

import java.util.LinkedHashMap;
import java.util.Map;

final class ScenePreprocessResponseMapper {

    // 工具类不需要实例化。
    private ScenePreprocessResponseMapper() {
    }

    // 转换场景预处理响应，并保持字段顺序便于前端联调。
    static Map<String, Object> toHttpData(PreprocessSceneReply reply) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("sceneId", reply.getSceneId());
        data.put("sampleId", reply.getSampleId());
        data.put("sceneSampleFileId", reply.getSceneSampleFileId());
        data.put("imageFileId", reply.getImageFileId());
        data.put("pointCloudFileId", reply.getPointCloudFileId());
        data.put("preImageFileId", reply.getPreImageFileId());
        data.put("postImageFileId", reply.getPostImageFileId());
        data.put("preprocessVersion", reply.getPreprocessVersion());
        data.put("manifestRegistered", reply.getManifestRegistered());
        data.put("checksumSha256", reply.getChecksumSha256());
        data.put("sceneSampleFileName", reply.getSceneSampleFileName());
        data.put("status", reply.getStatus());
        return data;
    }
}
