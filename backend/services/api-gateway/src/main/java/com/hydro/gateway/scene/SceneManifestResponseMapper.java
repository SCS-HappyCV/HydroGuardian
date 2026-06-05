// 场景资产清单响应映射器。
// 将 case-service 的 gRPC 响应转换为前端稳定使用的 HTTP JSON 字段。
package com.hydro.gateway.scene;

import com.hydro.grpc.casev1.SceneManifestReply;

import java.util.LinkedHashMap;
import java.util.Map;

final class SceneManifestResponseMapper {

    // 工具类不需要实例化。
    private SceneManifestResponseMapper() {
    }

    // 转换场景清单响应，并保持字段顺序便于前端调试。
    static Map<String, Object> toHttpData(SceneManifestReply reply) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("sceneId", reply.getSceneId());
        data.put("sampleId", reply.getSampleId());
        data.put("sceneSampleFileId", reply.getSceneSampleFileId());
        data.put("imageFileId", reply.getImageFileId());
        data.put("pointCloudFileId", reply.getPointCloudFileId());
        data.put("preImageFileId", reply.getPreImageFileId());
        data.put("postImageFileId", reply.getPostImageFileId());
        data.put("preprocessVersion", reply.getPreprocessVersion());
        data.put("checksumSha256", reply.getChecksumSha256());
        data.put("schemaVersion", reply.getSchemaVersion());
        data.put("createdAt", reply.getCreatedAt());
        data.put("updatedAt", reply.getUpdatedAt());
        return data;
    }
}
