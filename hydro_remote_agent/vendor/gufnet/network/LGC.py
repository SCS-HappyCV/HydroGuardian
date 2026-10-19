import torch.nn as nn
import torch

class DepthwiseConv1D(nn.Module):
    """
    1D深度可分离卷积：用于点云序列的局部位置增强（LPE）
    适配点云数据的1D序列结构，提取局部邻域特征
    """

    def __init__(self, in_channels, kernel_size=3, padding=1):
        super(DepthwiseConv1D, self).__init__()
        self.depthwise_conv = nn.Conv1d(
            in_channels, in_channels, kernel_size=kernel_size,
            padding=padding, groups=in_channels
        )
        nn.init.constant_(self.depthwise_conv.weight, 1.)
        if self.depthwise_conv.bias is not None:
            nn.init.constant_(self.depthwise_conv.bias, 0.)

    def forward(self, x):
        return self.depthwise_conv(x)


class GlobalContextModule(nn.Module):
    """
    轻量级全局上下文模块：通过全局池化+广播实现O(N)复杂度的全局建模
    避免O(N²)的注意力计算，同时保留全局语义信息
    """

    def __init__(self, dim):
        super(GlobalContextModule, self).__init__()
        self.global_proj = nn.Sequential(
            nn.Linear(dim, dim // 4),
            nn.ReLU(True),
            nn.Linear(dim // 4, dim),
            nn.Sigmoid()
        )

    def forward(self, x):
        """
        输入: x - [B, N, C]
        输出: 全局上下文增强的特征 [B, N, C]
        """
        # 全局平均池化: [B, N, C] -> [B, 1, C]
        global_feat = x.mean(dim=1, keepdim=True)
        # 生成通道注意力权重: [B, 1, C]
        attn_weights = self.global_proj(global_feat)
        # 广播乘法实现全局调制: [B, N, C] * [B, 1, C] -> [B, N, C]
        return x * attn_weights


class LGCBlock(nn.Module):
    """
    增强版局部位置增强模块（LPE-Block）
    核心设计：多尺度局部卷积 + 轻量级全局上下文

    改进点：
    1. 多尺度深度可分离卷积：捕获不同范围的局部特征
    2. 全局上下文模块：O(N)复杂度的全局建模，弥补无自注意力的缺陷
    3. 残差连接 + LayerNorm：稳定训练

    复杂度：O(N)，显存友好，适合大规模点云
    """

    def __init__(self, dim, use_lpe=True, use_global_context=True):
        super(LGCBlock, self).__init__()
        self.use_lpe = use_lpe
        self.use_global_context = use_global_context

        self.norm1 = nn.LayerNorm(dim)
        self.norm2 = nn.LayerNorm(dim)

        # 局部位置增强：多尺度深度可分离卷积
        if use_lpe:
            self.lpe_conv1 = DepthwiseConv1D(dim, kernel_size=3, padding=1)
            self.lpe_conv2 = DepthwiseConv1D(dim, kernel_size=5, padding=2)
            self.lpe_conv3 = DepthwiseConv1D(dim, kernel_size=7, padding=3)
            self.lpe_fusion = nn.Linear(dim * 3, dim)

        # 全局上下文模块：轻量级全局建模
        if use_global_context:
            self.global_context = GlobalContextModule(dim)

        # FFN（前馈网络）
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 2),
            nn.GELU(),
            nn.Linear(dim * 2, dim),
        )

    def forward(self, x):
        """
        输入: x - [N, C] 点云特征（N=点数，C=通道数）
        输出: [N, C] 增强后的点云特征
        """
        # 添加batch维度: [N, C] -> [1, N, C]
        if x.dim() == 2:
            x = x.unsqueeze(0)
            squeeze_output = True
        else:
            squeeze_output = False

        B, N, C = x.shape

        # LPE: 多尺度局部位置增强
        if self.use_lpe:
            x_norm = self.norm1(x)
            # [B, N, C] -> [B, C, N]
            x_conv = x_norm.permute(0, 2, 1)
            # 多尺度卷积
            lpe1 = self.lpe_conv1(x_conv)  # kernel=3
            lpe2 = self.lpe_conv2(x_conv)  # kernel=5
            lpe3 = self.lpe_conv3(x_conv)  # kernel=7
            # 融合: [B, C*3, N] -> [B, N, C*3] -> [B, N, C]
            lpe_cat = torch.cat([lpe1, lpe2, lpe3], dim=1).permute(0, 2, 1)
            lpe_out = self.lpe_fusion(lpe_cat)
            x = x + lpe_out  # 残差连接

        # 全局上下文增强
        if self.use_global_context:
            x = x + self.global_context(x)  # 残差连接

        # FFN
        x = x + self.ffn(self.norm2(x))

        if squeeze_output:
            x = x.squeeze(0)  # [1, N, C] -> [N, C]

        return x
