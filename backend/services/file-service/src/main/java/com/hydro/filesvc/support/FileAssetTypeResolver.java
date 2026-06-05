// 文件资产类型解析器。
// 统一把前端传入的 fileType、MIME 类型和文件扩展名归一成后端可查询的业务类型。
package com.hydro.filesvc.support;

import java.util.Locale;
import java.util.Set;

public final class FileAssetTypeResolver {

    private static final Set<String> ALLOWED_TYPES = Set.of(
            "image",
            "point_cloud",
            "scene_sample",
            "change_mask",
            "evidence_artifact",
            "generic"
    );

    private static final Set<String> IMAGE_EXTENSIONS = Set.of(
            ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"
    );

    private static final Set<String> POINT_CLOUD_EXTENSIONS = Set.of(
            ".las", ".laz", ".ply", ".pcd", ".xyz", ".pts", ".e57", ".bin"
    );

    // 工具类不需要实例化。
    private FileAssetTypeResolver() {
    }

    // 解析业务文件类型；显式 fileType 优先，否则按 MIME 类型和扩展名推断。
    public static String resolve(String requestedType, String fileName, String contentType) {
        String normalized = normalize(requestedType);
        if (!normalized.isBlank()) {
            if (!ALLOWED_TYPES.contains(normalized)) {
                throw new IllegalArgumentException("unsupported file_type: " + requestedType);
            }
            return normalized;
        }
        String lowerContentType = contentType == null ? "" : contentType.toLowerCase(Locale.ROOT);
        String extension = extensionOf(fileName);
        if (lowerContentType.startsWith("image/") || IMAGE_EXTENSIONS.contains(extension)) {
            return "image";
        }
        if (POINT_CLOUD_EXTENSIONS.contains(extension)) {
            return "point_cloud";
        }
        if (".json".equals(extension)) {
            return "scene_sample";
        }
        return "generic";
    }

    // 将前端可能传入的大小写、短横线形式统一为下划线小写。
    private static String normalize(String value) {
        if (value == null) {
            return "";
        }
        return value.trim().toLowerCase(Locale.ROOT).replace("-", "_");
    }

    // 提取文件扩展名；没有扩展名时返回空字符串。
    private static String extensionOf(String fileName) {
        if (fileName == null) {
            return "";
        }
        String lower = fileName.toLowerCase(Locale.ROOT);
        int index = lower.lastIndexOf('.');
        if (index < 0 || index == lower.length() - 1) {
            return "";
        }
        return lower.substring(index);
    }
}
