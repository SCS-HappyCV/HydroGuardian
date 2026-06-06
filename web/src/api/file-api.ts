// 文件资产 API 封装：负责上传文件和查询 file-service 已登记的文件元数据。

import { API_PATHS, type FileAssetData, type FileAssetType } from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

// 上传图像、点云、SceneTensorSample 或证据文件。
export function uploadFile(file: File, fileType?: FileAssetType) {
  const formData = new FormData()
  formData.append('file', file)

  // fileType 为空时让后端按默认 generic 处理。
  if (fileType) {
    formData.append('fileType', fileType)
  }

  return httpClient.post<FileAssetData>(API_PATHS.files.upload, formData)
}

// 按 fileId 查询文件资产元数据。
export function getFile(fileId: string) {
  return httpClient.get<FileAssetData>(API_PATHS.files.detail(fileId))
}
