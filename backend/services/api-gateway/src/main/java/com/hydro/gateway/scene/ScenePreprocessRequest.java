// 场景预处理 HTTP 请求。
// 前端上传图像和点云后，把 fileId 交给 agent-service 生成 SceneTensorSample。
package com.hydro.gateway.scene;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ScenePreprocessRequest(
        // 场景业务 ID，后续 ExecuteTask 会用它查询 manifest。
        @NotBlank(message = "sceneId cannot be blank")
        String sceneId,
        // 样本业务 ID；为空时 agent-service 会默认使用 sceneId。
        String sampleId,
        // 主图像或正射图 fileId。
        @NotBlank(message = "imageFileId cannot be blank")
        String imageFileId,
        // 点云文件 fileId。
        @NotBlank(message = "pointCloudFileId cannot be blank")
        String pointCloudFileId,
        // 变化检测前时相图像 fileId。
        String preImageFileId,
        // 变化检测后时相图像 fileId。
        String postImageFileId,
        // 可选预处理版本；为空时 agent-service 使用默认版本。
        String preprocessVersion,
        // 可选图像尺寸；0 表示使用 agent-service 默认值。
        @Min(value = 0, message = "imageSize must be non-negative")
        @Max(value = 1024, message = "imageSize must be no more than 1024")
        Integer imageSize,
        // 可选最大点数；0 表示使用 agent-service 默认值。
        @Min(value = 0, message = "maxPoints must be non-negative")
        @Max(value = 200000, message = "maxPoints must be no more than 200000")
        Integer maxPoints
) {
}
