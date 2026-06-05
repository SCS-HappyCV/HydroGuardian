// 场景资产清单注册 HTTP 请求。
// 前端上传文件到 file-service 后，用这些 fileId 组装一个可被 agent-service 使用的场景样本清单。
package com.hydro.gateway.scene;

import jakarta.validation.constraints.NotBlank;

public record SceneManifestRequest(
        // 预处理后的 SceneTensorSample JSON 文件 ID，agent-service 会下载并校验它。
        @NotBlank(message = "sceneSampleFileId cannot be blank")
        String sceneSampleFileId,
        // 预处理样本业务 ID；为空时 case-service 会默认使用 sceneId。
        String sampleId,
        // 主图像或正射图文件 ID。
        String imageFileId,
        // 点云文件 ID。
        String pointCloudFileId,
        // 变化检测前时相图像文件 ID。
        String preImageFileId,
        // 变化检测后时相图像文件 ID。
        String postImageFileId,
        // 预处理流水线版本。
        String preprocessVersion,
        // 样本或清单校验和。
        String checksumSha256,
        // 清单协议版本。
        String schemaVersion
) {
}
