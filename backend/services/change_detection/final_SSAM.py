import math
import torch
import torch.nn as nn
import torch.nn.functional as F


#替换SSAM
class Spatial_Feature_Enhancement_Module(nn.Module):
    def __init__(self, in_d=64, out_d=64, reduction=2, group=4):
        super(Spatial_Feature_Enhancement_Module, self).__init__()
        self.in_d = in_d
        self.out_d = out_d
        self.mid_d = out_d * reduction
        self.group = group
        assert self.mid_d % self.group == 0, "fail to split groups"
        self.split_d = self.mid_d // group
        self.conv3x3 = nn.Sequential(
            nn.Conv2d(self.in_d, self.in_d, kernel_size=3, padding=1, stride=1),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU(inplace=True),
        )
        self.out_conv = nn.Sequential(
            nn.Conv2d(self.in_d, self.in_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU(inplace=True),
            nn.Conv2d(self.in_d, self.in_d, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU(inplace=True),
            nn.Conv2d(self.in_d, self.out_d, kernel_size=1, stride=1),
            nn.BatchNorm2d(self.out_d),
            nn.ReLU(inplace=True)
        )
        self.psconv1 = nn.Sequential(
            PSConv2d(self.in_d, self.in_d, kernel_size=3, stride=1, padding=1, parts=4),
            nn.BatchNorm2d(self.in_d),
            nn.ReLU(inplace=True),
        )

    def forward(self, x4, x5):
        x = self.conv3x3(x4 + F.interpolate(x5, scale_factor=(2, 2), mode="bilinear"))
        x = self.psconv1(x)
        x = self.out_conv(x)
        return x


class PSConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, parts=4, bias=False):
        super(PSConv2d, self).__init__()
        self.gwconv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, dilation, dilation, groups=parts, bias=bias)
        self.gwconv_shift = nn.Conv2d(in_channels, out_channels, kernel_size, stride, 2 * dilation, 2 * dilation, groups=parts, bias=bias)
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding, bias=bias)

        def backward_hook(grad):
            out = grad.clone()
            out[self.mask] = 0
            return out

        # self.mask = torch.zeros(self.conv.weight.shape).byte().cuda()
        self.mask = torch.zeros(self.conv.weight.shape, dtype=torch.bool).cuda()
        _in_channels = in_channels // parts
        _out_channels = out_channels // parts
        for i in range(parts):
            self.mask[i * _out_channels: (i + 1) * _out_channels, i * _in_channels: (i + 1) * _in_channels, : , :] = 1
            self.mask[(i + parts//2)%parts * _out_channels: ((i + parts//2)%parts + 1) * _out_channels, i * _in_channels: (i + 1) * _in_channels, :, :] = 1
        # self.conv.weight.data[self.mask] = 0
        self.conv.weight.data[self.mask] = 0
        self.conv.weight.register_hook(backward_hook)

    def forward(self, x):
        x1, x2 = x.chunk(2, dim=1)
        x_shift = self.gwconv_shift(torch.cat((x2, x1), dim=1))
        return self.gwconv(x) + self.conv(x) + x_shift


# PSConv-based Group Convolution
class PSGConv2d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1, dilation=1, groups=1, parts=4, bias=False):
        super(PSGConv2d, self).__init__()
        self.gwconv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, dilation, dilation, groups=groups * parts, bias=bias)
        self.gwconv_shift = nn.Conv2d(in_channels, out_channels, kernel_size, stride, 2 * dilation, 2 * dilation, groups=groups * parts, bias=bias)
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding, groups=groups, bias=bias)

        def backward_hook(grad):
            out = grad.clone()
            out[self.mask] = 0
            return out

        self.mask = torch.zeros(self.conv.weight.shape).byte().cuda()
        _in_channels = in_channels // (groups * parts)
        _out_channels = out_channels // (groups * parts)
        for i in range(parts):
            for j in range(groups):
                self.mask[(i + j * groups) * _out_channels: (i + j * groups + 1) * _out_channels, i * _in_channels: (i + 1) * _in_channels, : , :] = 1
                self.mask[((i + parts // 2) % parts + j * groups) * _out_channels: ((i + parts // 2) % parts + j * groups + 1) * _out_channels, i * _in_channels: (i + 1) * _in_channels, :, :] = 1
        self.conv.weight.data[self.mask] = 0
        self.conv.weight.register_hook(backward_hook)
        self.groups = groups

    def forward(self, x):
        x_split = (z.chunk(2, dim=1) for z in x.chunk(self.groups, dim=1))
        x_merge = torch.cat(tuple(torch.cat((x2, x1), dim=1) for (x1, x2) in x_split), dim=1)
        x_shift = self.gwconv_shift(x_merge)
        return self.gwconv(x) + self.conv(x) + x_shift
