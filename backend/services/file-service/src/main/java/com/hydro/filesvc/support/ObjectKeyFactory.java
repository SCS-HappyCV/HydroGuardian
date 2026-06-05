// MinIO 对象键生成器。
// 通过业务类型、日期、fileId 和安全文件名生成稳定且可排查的对象路径。
package com.hydro.filesvc.support;

import java.time.LocalDate;
import java.util.Locale;

public final class ObjectKeyFactory {

    // 工具类不需要实例化。
    private ObjectKeyFactory() {
    }

    // 生成形如 image/2026/06/04/file-xxx-name.png 的对象键。
    public static String build(String fileType, String fileId, String fileName) {
        LocalDate today = LocalDate.now();
        return String.format(
                Locale.ROOT,
                "%s/%04d/%02d/%02d/%s-%s",
                safeSegment(fileType),
                today.getYear(),
                today.getMonthValue(),
                today.getDayOfMonth(),
                safeSegment(fileId),
                sanitizeFileName(fileName)
        );
    }

    // 清理对象键目录片段，避免空格和特殊字符影响对象存储路径。
    private static String safeSegment(String value) {
        if (value == null || value.isBlank()) {
            return "generic";
        }
        return value.trim().toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_-]", "_");
    }

    // 清理原始文件名；保留常见点号、短横线和下划线，其他字符转成下划线。
    private static String sanitizeFileName(String fileName) {
        if (fileName == null || fileName.isBlank()) {
            return "upload.bin";
        }
        return fileName.trim().replaceAll("[^A-Za-z0-9._-]", "_");
    }
}
