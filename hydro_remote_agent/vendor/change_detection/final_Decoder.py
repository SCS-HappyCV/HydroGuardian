import torch
import math
from torch import nn
import torch.nn.functional as F

class SCIMadd(nn.Module):  #ECA共享权重 Cross-Layer Feature Modulation, CLFM
    def __init__(self, in_d):
        super(SCIMadd, self).__init__()
        self.in_d = in_d
        self.global_conv1 = nn.Sequential(
            nn.Conv2d(self.in_d, self.in_d, kernel_size=1, stride=1)
        )
        self.high_conv1 = nn.Sequential(
            nn.Conv2d(self.in_d, self.in_d, kernel_size=1, stride=1)
        )
        self.out_conv = nn.Sequential(
            nn.Conv2d(2 * self.in_d, self.in_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU(inplace=True)
        )
        self.conv1 = nn.Sequential(
            nn.Conv2d(self.in_d, self.in_d, 3, padding=1),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU()
        )
        self.conv2 =nn.Conv2d(4, 1, kernel_size=7, stride=1, padding=3)
        self.ECA1 = ECA(in_d)
        "新增"
        self.mid_d = in_d
        self.conv_high = nn.Conv2d(self.mid_d, self.mid_d, kernel_size=1, stride=1)
        self.conv_global = nn.Conv2d(self.mid_d, self.mid_d, kernel_size=1, stride=1)
        self.fusion = nn.Sequential(
            nn.Conv2d(self.mid_d, self.mid_d, kernel_size=3, stride=1, padding=1, groups=self.mid_d),
            nn.BatchNorm2d(self.mid_d),
            nn.ReLU(inplace=True),
        )
        self.cls = nn.Conv2d(self.mid_d, 1, kernel_size=1)

    def forward(self, low_context, high_context, global_context):
        batch, channels, height, width = low_context.size()
        high_context = self.conv1(F.interpolate(high_context, size=(height, width), mode='bilinear'))
        global_context = self.conv1(F.interpolate(global_context, size=(height, width), mode='bilinear'))
        high_context = self.high_conv1(high_context)
        global_context = self.global_conv1(global_context)
        low_context_1 = self.ECA1(high_context, low_context) #B*C*H*W
        low_context_2 = self.ECA1(global_context, low_context) #B*C*H*W
        low_context = torch.cat([low_context_1, low_context_2], dim=1)  # B, 2C, H, W
        low_context = self.out_conv(low_context)

        x_high = F.interpolate(self.conv_high(high_context), size=(height, width), mode="bilinear")
        global_context = F.interpolate(self.conv_global(global_context), size=(height, width), mode="bilinear")
        x_low = self.fusion(low_context + x_high + global_context)
        mask = self.cls(x_low)
        return x_low, mask


class Cross_layer_Attention_Modulation(nn.Module):
    def __init__(self, mid_d=320):
        super(Cross_layer_Attention_Modulation, self).__init__()
        self.mid_d = mid_d
        self.cra4 = SCIMadd(self.mid_d)
        self.cra3 = SCIMadd(self.mid_d)
        self.cra2 = SCIMadd(self.mid_d)
        self.cra1 = SCIMadd(self.mid_d)

    def forward(self, d1, d2, d3, d4, d5, gc_d4):
        # high-level
        # p4 = self.cra4(d4, d5, gc_d4)
        p4, mask_p4 = self.cra4(d4, d5, gc_d4)
        p3, mask_p3 = self.cra3(d3, p4, gc_d4)
        p2, mask_p2 = self.cra2(d2, p3, gc_d4)
        p1, mask_p1 = self.cra1(d1, p2, gc_d4)
        return mask_p1, mask_p2, mask_p3, mask_p4


class ECA(nn.Module):
    """
    高效的通道注意力模块 (ECA-Net)
    比SENet和CBAM中的通道注意力更轻量，且避免降维带来的信息损失。
    """
    def __init__(self, channels, gamma=2, b=1):
        super(ECA, self).__init__()
        self.channels = channels

        # 自适应计算一维卷积的核大小k
        t = int(abs((math.log(channels, 2) + b) / gamma))
        k = t if t % 2 else t + 1  # 确保k为奇数以便对称padding

        self.avg_pool = nn.AdaptiveAvgPool2d(1)
        # 使用1D卷积进行跨通道交互，参数量极少
        self.conv = nn.Conv1d(1, 1, kernel_size=k, padding=(k-1)//2, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x, z):
        # x shape: [batch_size, channels, height, width]
        batch_size, channels, height, width = x.size()

        # 特征描述符: [batch_size, channels, 1, 1]
        y = self.avg_pool(x)

        # 变换为1D卷积的输入格式: [batch_size, 1, channels]
        y = y.view(batch_size, 1, channels)

        # 1D卷积处理: [batch_size, 1, channels]
        y = self.conv(y)

        # Sigmoid激活: [batch_size, 1, channels]
        y = self.sigmoid(y)

        # 变换回原始格式: [batch_size, channels, 1, 1]
        y = y.view(batch_size, channels, 1, 1)

        # 应用注意力权重并返回
        return z * y.expand_as(z)
