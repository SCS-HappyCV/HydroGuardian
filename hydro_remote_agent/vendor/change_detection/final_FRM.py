import torch
import torch.nn as nn
import torch.nn.functional as F


class AdaptiveScaleProjector_Optimized(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(AdaptiveScaleProjector_Optimized, self).__init__()
        # 建立一个通用的卷积核心，用于特征转换
        # 先降维再卷积，减少参数量
        self.mid_channels = out_channels

        self.conv_adapt = nn.Sequential(
            nn.Conv2d(in_channels, self.mid_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(self.mid_channels),
            nn.ReLU(inplace=True),
            # 使用深度可分离卷积来处理空间信息，适应不同尺度
            nn.Conv2d(self.mid_channels, self.mid_channels, kernel_size=3, padding=1, groups=self.mid_channels, bias=False),
            nn.BatchNorm2d(self.mid_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x, target_size=None, scale_factor=None):
        # 1. 特征变换
        x = self.conv_adapt(x)

        if target_size is None and scale_factor is None:
            return x

        # [修复方案]：弃用 adaptive_avg_pool2d，改用 MaxPool 或 Interpolate
        # MaxPool 对变化检测(寻找显著差异)通常比 AvgPool 更好

        if scale_factor is not None and scale_factor < 1:
            # 下采样 (Downsample)
            # 方案 A: 使用 MaxPool (保留最强特征)
            if scale_factor == 0.5:
                x = F.max_pool2d(x, kernel_size=2, stride=2)
            elif scale_factor == 0.25:
                # 4倍下采样
                x = F.max_pool2d(x, kernel_size=4, stride=4)
            elif scale_factor == 0.125: # 1/8
                x = F.max_pool2d(x, kernel_size=8, stride=8)
            elif scale_factor == 0.0625: # 1/16
                x = F.max_pool2d(x, kernel_size=16, stride=16)
            else:
                # 兜底策略，还是用 interpolate (bilinear) 比 avg_pool好，因为它保留空间结构
                x = F.interpolate(x, size=target_size, mode='bilinear', align_corners=False)

        elif target_size is not None or (scale_factor is not None and scale_factor > 1):
            # 上采样 (Upsample) - 保持不变，双线性插值是标准的
            x = F.interpolate(x, size=target_size if target_size else None, scale_factor=scale_factor, mode='bilinear', align_corners=False)

        return x



# FeatureFusionModule 保持不变，或者应用之前的 Channel Attention 修改
class new1_FeatureFusionModule(nn.Module):
    # ...existing code...
    def __init__(self, fuse_d, id_d, out_d):
        super(new1_FeatureFusionModule, self).__init__()
        # ...existing code...
        self.fuse_d = fuse_d
        self.id_d = id_d
        self.out_d = out_d
        self.conv_fuse = nn.Sequential(
            nn.Conv2d(self.fuse_d, self.fuse_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.fuse_d),
            nn.ReLU(inplace=True),
            nn.Conv2d(self.fuse_d, self.fuse_d, kernel_size=3, stride=1, padding=1, groups=self.fuse_d),
            nn.BatchNorm2d(self.fuse_d),
            nn.ReLU(inplace=True),
            nn.Conv2d(self.fuse_d, self.out_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.out_d),
        )
        self.conv_identity = nn.Conv2d(self.id_d, self.out_d, kernel_size=1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, c_fuse, c):
        attention = self.sigmoid(self.conv_fuse(c_fuse))
        c = self.conv_identity(c)
        c_out = attention * c + c
        return c_out


class Adaptive_Scale_Reinforcement(nn.Module):
    def __init__(self, in_d=None, out_d=64):
        super(Adaptive_Scale_Reinforcement, self).__init__()
        if in_d is None:
            in_d = [16, 24, 32, 96, 320]
        self.in_d = in_d
        self.mid_d = out_d // 2
        self.out_d = out_d

        # [NEW] 2. 替换掉原来的 25 个独立的 Sequential，改为 5 个源投影器
        # 我们只需定义如何处理 Input，至于投向哪里，在 forward 里动态决定
        self.projectors = nn.ModuleList([
            AdaptiveScaleProjector_Optimized(in_ch, self.mid_d) for in_ch in self.in_d
        ])

        # fusion (保持不变，或者按照之前的建议修改)
        # 注意: 输入给 fusion 的通道数现在是 self.mid_d * 5
        self.conv_aggregation_s1 = new1_FeatureFusionModule(self.mid_d * 5, self.in_d[0], self.out_d)
        self.conv_aggregation_s2 = new1_FeatureFusionModule(self.mid_d * 5, self.in_d[1], self.out_d)
        self.conv_aggregation_s3 = new1_FeatureFusionModule(self.mid_d * 5, self.in_d[2], self.out_d)
        self.conv_aggregation_s4 = new1_FeatureFusionModule(self.mid_d * 5, self.in_d[3], self.out_d)
        self.conv_aggregation_s5 = new1_FeatureFusionModule(self.mid_d * 5, self.in_d[4], self.out_d)

    def forward(self, c1, c2, c3, c4, c5):
        inputs = [c1, c2, c3, c4, c5]

        # 获取每个尺度的空间尺寸 (H, W)
        shapes = [x.shape[2:] for x in inputs]

        # [NEW] 3. 动态计算投影矩阵
        # 矩阵结构: matrix[target_idx][source_idx]
        # 我们需要生成 5 个列表，每个列表包含来自 5 个源的特征，对应特定的 Target Scale

        # 第一步：先将所有 Input 统一变换到中间通道维度 (mid_d)
        # 这一步是参数共享的，大大减少了参数量
        projected_feats = [proj(x) for proj, x in zip(self.projectors, inputs)]

        # 第二步：空间对齐与收集
        # outputs_collections[i] 将存储用于合成 Scale i 的 list
        outputs_collections = [[], [], [], [], []]

        for source_idx, feat in enumerate(projected_feats):
            source_shape = shapes[source_idx]

            for target_idx in range(5):
                target_shape = shapes[target_idx]

                # 计算相对尺度因子
                # 例如 Source是Scale 1 (大图), Target是Scale 2 (小图), scale_factor < 1 -> Downsample
                # 注意: 假设 index 越大 feature map 越小 (通常 c1是最大图, c5是最小图)
                # stride 关系通常是 2 的幂次

                if source_idx == target_idx:
                    # 同尺度，直接添加
                    res = feat
                else:
                    # 异尺度，进行动态 resize
                    # 使用 adaptive_avg_pool 或者 interpolate
                    # 传入 target_shape 确保像素级对齐
                    if source_idx < target_idx:
                        # Source 比 Target 大 -> 需要下采样 (Downsample)
                        res = F.adaptive_avg_pool2d(feat, target_shape)
                    else:
                        # Source 比 Target 小 -> 需要上采样 (Upsample)
                        res = F.interpolate(feat, size=target_shape, mode='bilinear', align_corners=False)

                outputs_collections[target_idx].append(res)

        # 第三步：融合
        s1 = self.conv_aggregation_s1(torch.cat(outputs_collections[0], dim=1), c1)
        s2 = self.conv_aggregation_s2(torch.cat(outputs_collections[1], dim=1), c2)
        s3 = self.conv_aggregation_s3(torch.cat(outputs_collections[2], dim=1), c3)
        s4 = self.conv_aggregation_s4(torch.cat(outputs_collections[3], dim=1), c4)
        s5 = self.conv_aggregation_s5(torch.cat(outputs_collections[4], dim=1), c5)

        return s1, s2, s3, s4, s5
