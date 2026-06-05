// 已写入对象存储的文件摘要。
// gRPC 服务用它填充 file_asset 元数据和响应字段。
package com.hydro.filesvc.storage;

public record StoredObject(
        String objectKey,
        String downloadUrl,
        String checksumSha256,
        long size
) {
}
