// 场景 API 封装：负责真实场景预处理和 scene manifest 注册/查询。

import {
  API_PATHS,
  type SceneManifestData,
  type SceneManifestRequestData,
  type ScenePreprocessRequestData,
  type ScenePreprocessResponseData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

// 调用 agent-service 预处理图像和点云，生成 SceneTensorSample JSON。
export function preprocessScene(data: ScenePreprocessRequestData) {
  return httpClient.post<ScenePreprocessResponseData>(API_PATHS.scenes.preprocess, data)
}

// 注册或更新指定 sceneId 的场景资产清单。
export function createSceneManifest(sceneId: string, data: SceneManifestRequestData) {
  return httpClient.post<SceneManifestData>(API_PATHS.scenes.manifest(sceneId), data)
}

// 查询指定 sceneId 的场景资产清单。
export function getSceneManifest(sceneId: string) {
  return httpClient.get<SceneManifestData>(API_PATHS.scenes.manifest(sceneId))
}
