from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class SparseBasicBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, indice_key: str, spconv_module):
        super().__init__()
        spconv = spconv_module
        self.layers_in = spconv.SparseSequential(
            spconv.SubMConv3d(in_channels, out_channels, 1, indice_key=indice_key, bias=False),
            nn.BatchNorm1d(out_channels),
        )
        self.layers = spconv.SparseSequential(
            spconv.SubMConv3d(in_channels, out_channels, 3, indice_key=indice_key, bias=False),
            nn.BatchNorm1d(out_channels),
            nn.LeakyReLU(0.1),
            spconv.SubMConv3d(out_channels, out_channels, 3, indice_key=indice_key, bias=False),
            nn.BatchNorm1d(out_channels),
        )

    def forward(self, x):
        identity = self.layers_in(x)
        output = self.layers(x)
        return output.replace_feature(F.leaky_relu(output.features + identity.features, 0.1))


class voxelization(nn.Module):
    def __init__(self, coors_range_xyz, spatial_shape, scale_list):
        super().__init__()
        self.spatial_shape = spatial_shape
        self.scale_list = list(scale_list) + [1]
        self.coors_range_xyz = coors_range_xyz

    @staticmethod
    def sparse_quantize(pc, coors_range, spatial_shape):
        idx = spatial_shape * (pc - coors_range[0]) / (coors_range[1] - coors_range[0])
        return idx.long()

    def forward(self, data_dict):
        import torch_scatter

        pc = data_dict["points"][:, :3]

        for scale in self.scale_list:
            xidx = self.sparse_quantize(pc[:, 0], self.coors_range_xyz[0], np.ceil(self.spatial_shape[0] / scale))
            yidx = self.sparse_quantize(pc[:, 1], self.coors_range_xyz[1], np.ceil(self.spatial_shape[1] / scale))
            zidx = self.sparse_quantize(pc[:, 2], self.coors_range_xyz[2], np.ceil(self.spatial_shape[2] / scale))

            bxyz_indx = torch.stack([data_dict["batch_idx"], xidx, yidx, zidx], dim=-1).long()
            unq, unq_inv, _ = torch.unique(bxyz_indx, return_inverse=True, return_counts=True, dim=0)
            unq = torch.cat([unq[:, 0:1], unq[:, [3, 2, 1]]], dim=1)
            data_dict[f"scale_{scale}"] = {
                "full_coors": bxyz_indx,
                "coors_inv": unq_inv,
                "coors": unq.type(torch.int32),
            }
        return data_dict


class voxel_3d_generator(nn.Module):
    def __init__(self, in_channels, out_channels, coors_range_xyz, spatial_shape):
        super().__init__()
        self.spatial_shape = spatial_shape
        self.coors_range_xyz = coors_range_xyz
        self.PPmodel = nn.Sequential(
            nn.Linear(in_channels + 6, out_channels),
            nn.ReLU(True),
            nn.Linear(out_channels, out_channels),
        )

    def prepare_input(self, point, grid_ind, inv_idx):
        import torch_scatter

        pc_mean = torch_scatter.scatter_mean(point[:, :3], inv_idx, dim=0)[inv_idx]
        nor_pc = point[:, :3] - pc_mean

        coors_range_xyz = torch.tensor(self.coors_range_xyz, device=point.device)
        cur_grid_size = torch.tensor(self.spatial_shape, device=point.device)
        crop_range = coors_range_xyz[:, 1] - coors_range_xyz[:, 0]
        intervals = crop_range / cur_grid_size
        voxel_centers = grid_ind.float() * intervals + coors_range_xyz[:, 0]
        center_to_point = point[:, :3] - voxel_centers

        pc_feature = torch.cat((point, nor_pc, center_to_point), dim=1)
        return pc_feature

    def forward(self, data_dict):
        import spconv.pytorch as spconv
        import torch_scatter

        pt_fea = self.prepare_input(
            data_dict["points"],
            data_dict["scale_1"]["full_coors"][:, 1:],
            data_dict["scale_1"]["coors_inv"],
        )
        pt_fea = self.PPmodel(pt_fea)

        features = torch_scatter.scatter_mean(pt_fea, data_dict["scale_1"]["coors_inv"], dim=0)
        data_dict["sparse_tensor"] = spconv.SparseConvTensor(
            features=features,
            indices=data_dict["scale_1"]["coors"].int(),
            spatial_shape=np.int32(self.spatial_shape)[::-1].tolist(),
            batch_size=data_dict["batch_size"],
        )

        data_dict["coors"] = data_dict["scale_1"]["coors"]
        data_dict["coors_inv"] = data_dict["scale_1"]["coors_inv"]
        data_dict["full_coors"] = data_dict["scale_1"]["full_coors"]
        return data_dict


class point_encoder(nn.Module):
    def __init__(self, in_channels, out_channels, scale):
        super().__init__()
        self.scale = scale
        self.layer_in = nn.Sequential(
            nn.Linear(in_channels, out_channels),
            nn.LeakyReLU(0.1, True),
        )
        self.PPmodel = nn.Sequential(
            nn.Linear(in_channels, out_channels // 2),
            nn.LeakyReLU(0.1, True),
            nn.BatchNorm1d(out_channels // 2),
            nn.Linear(out_channels // 2, out_channels // 2),
            nn.LeakyReLU(0.1, True),
            nn.BatchNorm1d(out_channels // 2),
            nn.Linear(out_channels // 2, out_channels),
            nn.LeakyReLU(0.1, True),
        )
        self.layer_out = nn.Sequential(
            nn.Linear(2 * out_channels, out_channels),
            nn.LeakyReLU(0.1, True),
            nn.Linear(out_channels, out_channels),
        )

    @staticmethod
    def downsample(coors, p_fea, scale=2):
        import torch_scatter

        batch = coors[:, 0:1]
        coors = coors[:, 1:] // scale
        inv = torch.unique(torch.cat([batch, coors], 1), return_inverse=True, dim=0)[1]
        return torch_scatter.scatter_mean(p_fea, inv, dim=0), inv

    def forward(self, features, data_dict):
        import torch_scatter

        output, inv = self.downsample(data_dict["coors"], features, scale=self.scale)
        identity = self.layer_in(features)
        output = self.PPmodel(output)[inv]
        output = torch.cat([identity, output], dim=1)

        v_feat = torch_scatter.scatter_mean(
            self.layer_out(output[data_dict["coors_inv"]]),
            data_dict[f"scale_{self.scale}"]["coors_inv"],
            dim=0,
        )
        data_dict["coors"] = data_dict[f"scale_{self.scale}"]["coors"]
        data_dict["coors_inv"] = data_dict[f"scale_{self.scale}"]["coors_inv"]
        data_dict["full_coors"] = data_dict[f"scale_{self.scale}"]["full_coors"]
        return v_feat


class SPVBlock(nn.Module):
    def __init__(self, in_channels, out_channels, indice_key, scale, last_scale, spatial_shape):
        super().__init__()
        self.scale = scale
        self.indice_key = indice_key
        self.last_scale = last_scale
        self.spatial_shape = spatial_shape
        import spconv.pytorch as spconv

        # Do not wrap custom nn.Module SparseBasicBlock inside spconv.SparseSequential.
        # Otherwise spconv treats it as a dense module and passes Tensor instead of SparseConvTensor.
        self.v_block1 = SparseBasicBlock(in_channels, out_channels, self.indice_key, spconv)
        self.v_block2 = SparseBasicBlock(out_channels, out_channels, self.indice_key, spconv)
        self.p_enc = point_encoder(in_channels, out_channels, scale)

    def forward(self, data_dict):
        import spconv.pytorch as spconv
        import torch_scatter

        coors_inv_last = data_dict[f"scale_{self.last_scale}"]["coors_inv"]
        coors_inv = data_dict[f"scale_{self.scale}"]["coors_inv"]

        v_fea = self.v_block1(data_dict["sparse_tensor"])
        v_fea = self.v_block2(v_fea)
        v_fea_inv = torch_scatter.scatter_mean(v_fea.features[coors_inv_last], coors_inv, dim=0)

        p_fea = self.p_enc(
            features=data_dict["sparse_tensor"].features + v_fea.features,
            data_dict=data_dict,
        )

        data_dict["sparse_tensor"] = spconv.SparseConvTensor(
            features=p_fea + v_fea_inv,
            indices=data_dict["coors"],
            spatial_shape=self.spatial_shape,
            batch_size=data_dict["batch_size"],
        )

        return p_fea[coors_inv]


class SPVCNNFeatureEncoder(nn.Module):
    def __init__(
        self,
        input_dims: int,
        hidden_dim: int,
        scale_list: Tuple[int, ...],
        spatial_shape: Tuple[int, int, int],
        min_volume_space: Tuple[float, float, float],
        max_volume_space: Tuple[float, float, float],
    ) -> None:
        super().__init__()
        try:
            import spconv.pytorch as spconv  # noqa: F401
            import torch_scatter  # noqa: F401
        except Exception as exc:
            raise ImportError("SPVCNNFeatureEncoder requires spconv and torch_scatter.") from exc
        self.hidden_dim = hidden_dim
        self.input_dims = input_dims
        self.scale_list = tuple(scale_list)
        self.num_scales = len(self.scale_list)
        self.spatial_shape = np.array(spatial_shape)
        self.coors_range_xyz = [
            [float(min_volume_space[0]), float(max_volume_space[0])],
            [float(min_volume_space[1]), float(max_volume_space[1])],
            [float(min_volume_space[2]), float(max_volume_space[2])],
        ]
        self.strides = [int(scale / self.scale_list[0]) for scale in self.scale_list]

        self.voxelizer = voxelization(
            coors_range_xyz=self.coors_range_xyz,
            spatial_shape=self.spatial_shape,
            scale_list=list(self.scale_list),
        )
        self.voxel_3d_generator = voxel_3d_generator(
            in_channels=self.input_dims,
            out_channels=self.hidden_dim,
            coors_range_xyz=self.coors_range_xyz,
            spatial_shape=self.spatial_shape,
        )

        self.spv_enc = nn.ModuleList()
        for i in range(self.num_scales):
            self.spv_enc.append(
                SPVBlock(
                    in_channels=self.hidden_dim,
                    out_channels=self.hidden_dim,
                    indice_key="spv_" + str(i),
                    scale=self.scale_list[i],
                    last_scale=self.scale_list[i - 1] if i > 0 else 1,
                    spatial_shape=np.int32(self.spatial_shape // self.strides[i])[::-1].tolist(),
                )
            )

    def forward(self, data_dict):
        with torch.no_grad():
            data_dict = self.voxelizer(data_dict)
        data_dict = self.voxel_3d_generator(data_dict)

        enc_feats = []
        for i in range(self.num_scales):
            enc_feats.append(self.spv_enc[i](data_dict))
        return torch.cat(enc_feats, dim=1)
