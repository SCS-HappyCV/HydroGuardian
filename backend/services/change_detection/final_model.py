import torch
import torch.nn as nn
import torch.nn.functional as F
import MobileNetV2
from final_SSAM import Spatial_Feature_Enhancement_Module
from final_Decoder import Cross_layer_Attention_Modulation
from final_FRM import Adaptive_Scale_Reinforcement;

class GroupFusion(nn.Module):
    def __init__(self, in_d, out_d):
        super(GroupFusion, self).__init__()
        self.in_d = in_d
        self.out_d = out_d
        self.conv = nn.Sequential(
            nn.Conv2d(self.in_d, self.out_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.out_d),
            nn.ReLU(inplace=True)
        )

    def forward(self, x1, x2):
        x = torch.abs(x1 - x2)
        x = self.conv(x)
        return x

class TemporalFusionModule(nn.Module):
    def __init__(self, in_d=64, out_d=64):
        super(TemporalFusionModule, self).__init__()
        self.in_d = in_d
        self.out_d = out_d
        # fusion
        self.gf_x1 = GroupFusion(self.in_d, self.out_d)
        self.gf_x2 = GroupFusion(self.in_d, self.out_d)
        self.gf_x3 = GroupFusion(self.in_d, self.out_d)
        self.gf_x4 = GroupFusion(self.in_d, self.out_d)
        self.gf_x5 = GroupFusion(self.in_d, self.out_d)

    def forward(self, x1_1, x1_2, x1_3, x1_4, x1_5, x2_1, x2_2, x2_3, x2_4, x2_5):
        # temporal fusion
        c1 = self.gf_x1(x1_1, x2_1)
        c2 = self.gf_x2(x1_2, x2_2)
        c3 = self.gf_x3(x1_3, x2_3)
        c4 = self.gf_x4(x1_4, x2_4)
        c5 = self.gf_x5(x1_5, x2_5)

        return c1, c2, c3, c4, c5

class final_BaseNet(nn.Module):       #new1_FRM+MySSAM+NewDecoder3
    def __init__(self, input_nc=3, output_nc=1):
        super(final_BaseNet, self).__init__()
        self.backbone = MobileNetV2.mobilenet_v2(pretrained=False)
        channles = [16, 24, 32, 96, 320]
        self.en_d = 32
        self.mid_d = self.en_d * 2
        self.frm = Adaptive_Scale_Reinforcement(channles, self.mid_d)
        self.tfm = TemporalFusionModule(self.mid_d, self.mid_d)
        self.gca = Spatial_Feature_Enhancement_Module(self.mid_d, self.mid_d)
        self.decoder = Cross_layer_Attention_Modulation(self.en_d * 2)

    def forward(self, x1, x2):
        # forward backbone resnet
        x1_1, x1_2, x1_3, x1_4, x1_5 = self.backbone(x1)
        x2_1, x2_2, x2_3, x2_4, x2_5 = self.backbone(x2)
        x1_1, x1_2, x1_3, x1_4, x1_5 = self.frm(x1_1, x1_2, x1_3, x1_4, x1_5)
        x2_1, x2_2, x2_3, x2_4, x2_5 = self.frm(x2_1, x2_2, x2_3, x2_4, x2_5)
        # temporal fusion
        c1, c2, c3, c4, c5 = self.tfm(x1_1, x1_2, x1_3, x1_4, x1_5, x2_1, x2_2, x2_3, x2_4, x2_5)
        # global context of high-level and low-level
        gc_c4 = self.gca(c4, c5)

        # fpn
        mask_p1, mask_p2, mask_p3, mask_p4 = self.decoder(c1, c2, c3, c4, c5, gc_c4)

        # change map
        mask_p1 = F.interpolate(mask_p1, scale_factor=(2, 2), mode='bilinear')
        mask_p1 = torch.sigmoid(mask_p1)
        mask_p2 = F.interpolate(mask_p2, scale_factor=(4, 4), mode='bilinear')
        mask_p2 = torch.sigmoid(mask_p2)
        mask_p3 = F.interpolate(mask_p3, scale_factor=(8, 8), mode='bilinear')
        mask_p3 = torch.sigmoid(mask_p3)
        mask_p4 = F.interpolate(mask_p4, scale_factor=(16, 16), mode='bilinear')
        mask_p4 = torch.sigmoid(mask_p4)

        return mask_p1, mask_p2, mask_p3, mask_p4
