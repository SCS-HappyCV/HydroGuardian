import torch.nn as nn
import torch.nn.functional as F
import torch


class PointwiseUncertaintyEstimator(nn.Module):
    """
    像素级/点级不确定性估计分支
    功能：为每个点独立预测对数方差 log(σ²)，构建空间不确定性图
    
    对应论文公式：
    u_m^{(i)} = log((σ_m^{(i)})²) = F_conv2(δ(F_conv1(X_m^{(i)})))
    
    Args:
        in_channels: 输入通道数
        reduction: 通道压缩比例（默认4）
    """

    def __init__(self, in_channels, reduction=4):
        super(PointwiseUncertaintyEstimator, self).__init__()
        hidden_dim = max(in_channels // reduction, 8)
        # 使用 Shared MLP 对每个点独立建模
        self.uncertainty_branch = nn.Sequential(
            nn.Linear(in_channels, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1)  # 输出标量不确定性
        )

    def forward(self, x):
        """
        Args:
            x: (N, C) 点云特征
        Returns:
            uncertainty: (N, 1) 每个点的对数方差（不确定性）
        """
        # 逐点预测不确定性 log(σ²)
        uncertainty = self.uncertainty_branch(x)  # (N, 1)
        return uncertainty


class PointUGAF(nn.Module):
    """
    不确定性引导自适应融合模块 (Uncertainty-Guided Adaptive Fusion)
    
    核心设计：
        - 像素级证据不确定性建模：为每个点独立估计不确定性
        - 空间方差反比加权：高不确定性 -> 低融合权重
        - 点级语义细化：抑制离群点和投影误差
    
    对应论文公式：
        M_I^{(i)} = exp(-u_I^{(i)}) / (exp(-u_I^{(i)}) + exp(-u_P^{(i)}))
        X_fuse^{(i)} = M_I^{(i)} ⊙ X_I^{(i)} + M_P^{(i)} ⊙ X_P^{(i)}
    
    Args:
        c1: 第一路输入特征通道数（图像特征）
        c2: 第二路输入特征通道数（点云特征，也是输出通道数）
    """

    def __init__(self, c1, c2):
        super(PointUGAF, self).__init__()
        
        # A. 像素级不确定性估计分支
        self.uncertainty_img = PointwiseUncertaintyEstimator(c1)
        self.uncertainty_pts = PointwiseUncertaintyEstimator(c2)
        
        # B. 点级语义细化
        self.conv = nn.Sequential(
            nn.Linear(c2, c2),
            nn.LayerNorm(c2),
            nn.ReLU(inplace=True)
        )
        # 空间重要性掩码生成
        self.point_attn = nn.Sequential(
            nn.Linear(c2, c2 // 4),
            nn.ReLU(inplace=True),
            nn.Linear(c2 // 4, 1),
            nn.Sigmoid()
        )

    def forward(self, x1, x2):
        """
        Args:
            x1: (N, c1) 图像特征（投影后）
            x2: (N, c2) 点云特征
        Returns:
            X_out: (N, c2) 融合后的特征
        """
        # ========== A. 像素级证据不确定性建模 ==========
        # 预测每个点的对数方差 log(σ²)
        u_img = self.uncertainty_img(x1)  # (N, 1)
        u_pts = self.uncertainty_pts(x2)  # (N, 1)
        
        # 基于空间方差反比的动态加权（Softmax over -u）
        # M_I = exp(-u_I) / (exp(-u_I) + exp(-u_P))
        neg_u = torch.cat([-u_img, -u_pts], dim=1)  # (N, 2)
        confidence_mask = F.softmax(neg_u, dim=1)   # (N, 2)
        
        M_img = confidence_mask[:, 0:1]  # (N, 1) 图像置信度掩码
        M_pts = confidence_mask[:, 1:2]  # (N, 1) 点云置信度掩码
        
        # 空间加权融合
        # X_fuse = M_I ⊙ X_I + M_P ⊙ X_P
        X_fuse = M_img * x1 + M_pts * x2  # (N, c2)
        
        # ========== B. 点级语义细化 ==========
        # 非线性特征变换
        X_fuse_conv = self.conv(X_fuse)
        
        # 空间重要性掩码
        point_weight = self.point_attn(X_fuse_conv)  # (N, 1)
        
        # 最终输出
        X_out = X_fuse_conv * point_weight
        
        return X_out


class UGAF_PointAdapter(nn.Module):
    """
    UGAF点云适配器：不确定性引导自适应融合

    核心设计：
        - 像素级不确定性感知：自适应处理局部模态失效
        - 空间方差反比加权：统计最优的特征融合

    Args:
        dim: 输入/输出特征维度

    适用场景：
        - 2D-3D多模态融合（图像+点云）
        - 水面/阴影等局部模态失效场景
    """

    def __init__(self, dim):
        super(UGAF_PointAdapter, self).__init__()
        self.dim = dim

        # 特征适配（当输入维度不一致时使用）
        self.adapt = nn.Sequential(
            nn.Linear(dim, dim),
            nn.LayerNorm(dim),
            nn.ReLU(inplace=True)
        )

        # UGAF路径：不确定性引导自适应融合
        self.ugaf = PointUGAF(dim, dim)

    def forward(self, img_feat, pts_feat):
        """
        Args:
            img_feat: (N, C) 2D图像特征（投影到点后）
            pts_feat: (N, C) 3D点云特征
        Returns:
            fused_feat: (N, C) 融合后的特征
        """
        # 特征适配
        x1 = self.adapt(img_feat)  # 2D特征
        x2 = pts_feat              # 3D特征

        # UGAF 不确定性引导融合
        fused = self.ugaf(x1, x2)

        return fused


# ============ 保留原有接口的兼容性别名 ============
class PointSimpleAttention(nn.Module):
    """
    [已废弃] 原全局通道注意力模块，保留用于向后兼容
    建议使用 PointwiseUncertaintyEstimator 替代
    """

    def __init__(self, in_channels, reduction=16):
        super(PointSimpleAttention, self).__init__()
        self.fc1 = nn.Linear(in_channels, max(in_channels // reduction, 8))
        self.fc2 = nn.Linear(max(in_channels // reduction, 8), in_channels)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        gap = x.mean(dim=0)
        attention = F.relu(self.fc1(gap))
        attention = self.sigmoid(self.fc2(attention))
        return attention.unsqueeze(0)


# 兼容性别名
PointACMF = PointUGAF
ACMF_PointAdapter = UGAF_PointAdapter