#!/usr/bin/env python
# encoding: utf-8

import os
import torch
import yaml
import json
import numpy as np
import pytorch_lightning as pl

from datetime import datetime
from pytorch_lightning.metrics import Accuracy
from torch.optim.lr_scheduler import ReduceLROnPlateau, StepLR, CosineAnnealingWarmRestarts, CosineAnnealingLR
from utils.metric_util import IoU
from utils.schedulers import cosine_schedule_with_warmup

try:
    import laspy
except ImportError:
    laspy = None


class LightningBaseModel(pl.LightningModule):
    def __init__(self, args, criterion):
        super().__init__()
        self.args = args
        self.criterion = criterion
        self.train_acc = Accuracy()
        self.val_acc = Accuracy(compute_on_step=False)
        self.val_iou = IoU(self.args['dataset_params'], compute_on_step=False)

        if self.args['submit_to_server']:
            self.submit_dir = os.path.dirname(self.args['checkpoint']) + '/submit_' + datetime.now().strftime('%Y_%m_%d')
            with open(self.args['dataset_params']['label_mapping'], 'r') as stream:
                self.mapfile = yaml.safe_load(stream)

        self.ignore_label = self.args['dataset_params']['ignore_label']

    def configure_optimizers(self):
        if self.args['train_params']['optimizer'] == 'Adam':
            optimizer = torch.optim.Adam(self.parameters(),
                                         lr=self.args['train_params']["learning_rate"])
        elif self.args['train_params']['optimizer'] == 'SGD':
            optimizer = torch.optim.SGD(self.parameters(),
                                        lr=self.args['train_params']["learning_rate"],
                                        momentum=self.args['train_params']["momentum"],
                                        weight_decay=self.args['train_params']["weight_decay"],
                                        nesterov=self.args['train_params']["nesterov"])
        else:
            raise NotImplementedError

        if self.args['train_params']["lr_scheduler"] == 'StepLR':
            lr_scheduler = StepLR(
                optimizer,
                step_size=self.args['train_params']["decay_step"],
                gamma=self.args['train_params']["decay_rate"]
            )
        elif self.args['train_params']["lr_scheduler"] == 'ReduceLROnPlateau':
            lr_scheduler = ReduceLROnPlateau(
                optimizer,
                mode='max',
                factor=self.args['train_params']["decay_rate"],
                patience=self.args['train_params']["decay_step"],
                verbose=True
            )
        elif self.args['train_params']["lr_scheduler"] == 'CosineAnnealingLR':
            lr_scheduler = CosineAnnealingLR(
                optimizer,
                T_max=self.args['train_params']['max_num_epochs']-4,
                eta_min=1e-5,
            )
        elif self.args['train_params']["lr_scheduler"] == 'CosineAnnealingWarmRestarts':
            from functools import partial
            lr_scheduler = torch.optim.lr_scheduler.LambdaLR(
                optimizer, lr_lambda=partial(
                    cosine_schedule_with_warmup,
                    num_epochs=self.args['train_params']['max_num_epochs'],
                    batch_size=self.args['dataset_params']['train_data_loader']['batch_size'],
                    dataset_size=self.args['dataset_params']['training_size'],
                    num_gpu=len(self.args.gpu)
                ),
            )
        else:
            raise NotImplementedError

        scheduler = {
            'scheduler': lr_scheduler,
            'interval': 'step' if self.args['train_params']["lr_scheduler"] == 'CosineAnnealingWarmRestarts' else 'epoch',
            'frequency': 1
        }

        return {
            'optimizer': optimizer,
            'lr_scheduler': scheduler,
            'monitor': self.args.monitor,
        }

    def forward(self, data):
        pass

    @staticmethod
    def _normalize_origin_len(origin_len):
        if torch.is_tensor(origin_len):
            return int(origin_len.reshape(-1)[0].item())
        if isinstance(origin_len, np.ndarray):
            return int(origin_len.reshape(-1)[0])
        if isinstance(origin_len, (list, tuple)):
            return int(origin_len[0])
        return int(origin_len)

    @staticmethod
    def _split_path_components(path):
        normalized = str(path).replace('\\', '/')
        return [item for item in normalized.split('/') if item]

    def _build_text_prediction_path(self, path):
        components = self._split_path_components(path)
        if components:
            filename = os.path.splitext(components[-1])[0] + '.txt'
        else:
            filename = 'prediction.txt'

        parent = components[-2] if len(components) >= 2 else 'default'
        grandparent = components[-3] if len(components) >= 3 else 'default'
        technical_dirs = {'velodyne', 'velodyne_reduced', 'image', 'image_2', 'lidar', 'laz', 'las'}

        if parent in technical_dirs:
            rel_parts = [grandparent]
        elif grandparent in {'train', 'val', 'test'}:
            rel_parts = [grandparent, parent]
        else:
            rel_parts = [grandparent]

        return os.path.join(self.submit_dir, 'predictions', *rel_parts, filename)

    def _mapped_to_original_labels(self, mapped_prediction):
        mapped_prediction = np.asarray(mapped_prediction, dtype=np.int32).reshape(-1)
        inv_map = self.mapfile.get('learning_map_inv', {})
        if not inv_map:
            return mapped_prediction

        inv_map = {int(k): int(v) for k, v in inv_map.items()}
        return np.vectorize(lambda x: inv_map.get(int(x), int(x)), otypes=[np.int32])(mapped_prediction)

    def _resolve_export_labels_and_rgb(self, mapped_prediction, use_bgr_color_map=False):
        mapped_prediction = np.asarray(mapped_prediction, dtype=np.int32).reshape(-1)
        original_prediction = self._mapped_to_original_labels(mapped_prediction)

        color_map = {
            int(k): np.asarray(v, dtype=np.float32)
            for k, v in self.mapfile.get('color_map', {}).items()
        }
        color_keys = set(color_map.keys())
        mapped_keys = set(int(v) for v in np.unique(mapped_prediction))
        original_keys = set(int(v) for v in np.unique(original_prediction))

        mapped_color_available = mapped_keys.issubset(color_keys)
        original_color_available = original_keys.issubset(color_keys)

        if mapped_color_available and not original_color_available:
            export_label = mapped_prediction
            color_lookup = mapped_prediction
        elif original_color_available:
            export_label = original_prediction
            color_lookup = original_prediction
        elif mapped_color_available:
            export_label = mapped_prediction
            color_lookup = mapped_prediction
        else:
            export_label = original_prediction
            color_lookup = original_prediction

        rgb = np.zeros((len(color_lookup), 3), dtype=np.float32)
        for idx, label in enumerate(color_lookup):
            color = color_map.get(int(label))
            if color is None:
                continue
            if use_bgr_color_map and len(color) >= 3:
                rgb[idx] = [color[2], color[1], color[0]]
            else:
                rgb[idx] = color[:3]

        return export_label.astype(np.int32, copy=False), rgb

    @staticmethod
    def _is_missing_laz_backend_error(exc):
        message = str(exc).lower()
        return (
            "no lazbackend selected" in message
            or "cannot decompress data" in message
            or ("laz" in message and "backend" in message)
        )

    def _warn_laz_backend_missing(self, path, exc):
        warned = getattr(self, '_laz_backend_warned', False)
        if warned:
            return
        self._laz_backend_warned = True
        print(
            "Warning: failed to read LAZ/LAS with laspy while exporting predictions.\n"
            f"Path: {path}\n"
            f"Reason: {exc}\n"
            "Falling back to available coordinates. "
            "For exact world coordinates, install a LAZ backend:\n"
            "  pip install \"laspy[lazrs]\""
        )

    def _load_original_xyz_from_path(self, path, origin_len):
        origin_len = self._normalize_origin_len(origin_len)
        if not path:
            return None

        lower_path = str(path).lower()
        xyz = None
        if lower_path.endswith('.pth'):
            raw_data = torch.load(path)
            if isinstance(raw_data, torch.Tensor):
                raw_data = raw_data.detach().cpu().numpy()
            else:
                raw_data = np.asarray(raw_data)
            xyz = raw_data[:origin_len, :3].astype(np.float32, copy=False)
        elif lower_path.endswith('.bin'):
            raw_data = np.fromfile(path, dtype=np.float32).reshape((-1, 4))
            xyz = raw_data[:origin_len, :3].astype(np.float32, copy=False)
        elif lower_path.endswith(('.las', '.laz')) and laspy is not None:
            try:
                las = laspy.read(path)
            except Exception as exc:
                if self._is_missing_laz_backend_error(exc):
                    self._warn_laz_backend_missing(path, exc)
                    return None
                raise
            xyz = np.stack([
                np.asarray(las.x, dtype=np.float32),
                np.asarray(las.y, dtype=np.float32),
                np.asarray(las.z, dtype=np.float32),
            ], axis=1)[:origin_len]

        return xyz


    def training_step(self, data_dict, batch_idx):
        data_dict['sparse_label'] = data_dict['targets'].F.long().squeeze(1)
        data_dict = self.forward(data_dict)

        data_dict['targets'] = data_dict['targets'].F.squeeze(1)
        self.train_acc(data_dict['sparse_logits'].argmax(1)[data_dict['targets'] != self.ignore_label],
                    data_dict['targets'][data_dict['targets'] != self.ignore_label])
        self.log('train/acc', self.train_acc, on_epoch=True)
        self.log('train/loss_sparse', data_dict['loss_sparse'])
        self.log('train/loss_main_ce', data_dict['loss_main_ce'])
        self.log('train/loss_main_lovasz', data_dict['loss_main_lovasz'])

        return data_dict['loss']


    def validation_step(self, data_dict, batch_idx):
        data_dict['sparse_label'] = data_dict['targets'].F.long().squeeze(1)
        data_dict = self.forward(data_dict)

        indices = data_dict['ref_index'].F
        raw_labels = data_dict['targets_mapped'].F[data_dict['targets_mapped'].C[:, -1] == 0].squeeze(1).cpu()
        origin_len = data_dict['origin_len']
        vote_logits = torch.zeros((len(raw_labels), self.num_classes))

        invs = data_dict['inverse_map']
        all_labels = data_dict['targets_mapped']
        _outputs = []
        _targets = []
        for idx in range(int(invs.C[:, -1].max() + 1)):
            cur_scene_pts = (data_dict['lidar'].C[:, -1] == idx).cpu().numpy()
            cur_inv = invs.F[invs.C[:, -1] == idx].cpu().numpy()
            cur_label = (all_labels.C[:, -1] == idx).cpu().numpy()
            outputs_mapped = data_dict['sparse_logits'][cur_scene_pts][cur_inv]
            targets_mapped = all_labels.F[cur_label]
            _outputs.append(outputs_mapped)
            _targets.append(targets_mapped)
        prediction_mapped = torch.cat(_outputs, 0)

        if self.args['test']:
            vote_logits.index_add_(0, indices.cpu(), prediction_mapped.cpu())
            prediction = vote_logits.argmax(1).cpu()
            if self.args['dataset_params']['pc_dataset_type'] == 'SemanticKITTI_multiscan':
                prediction = prediction[:origin_len]
                raw_labels = raw_labels[:origin_len]
        else:
            prediction = prediction_mapped.argmax(1).cpu()
            raw_labels = torch.cat(_targets, 0).squeeze(1).cpu()

        if self.ignore_label != 0:
            prediction = prediction[raw_labels != self.ignore_label]
            raw_labels = raw_labels[raw_labels != self.ignore_label]
            prediction += 1
            raw_labels += 1

        self.val_acc(prediction, raw_labels)
        self.log('val/acc', self.val_acc, on_epoch=True)
        self.val_iou(prediction.cpu().detach().numpy(),
                     raw_labels.cpu().detach().numpy(),
                     )

        return data_dict['loss']


    def test_step(self, data_dict, batch_idx):
        path = data_dict['root'][0]
        data_dict['sparse_label'] = data_dict['targets'].F.long().squeeze(1)
        data_dict = self.forward(data_dict)

        indices = data_dict['ref_index'].F
        raw_labels = data_dict['targets_mapped'].F[data_dict['targets_mapped'].C[:, -1] == 0].squeeze(1).cpu()
        origin_len = data_dict['origin_len']
        vote_logits = torch.zeros((len(raw_labels), self.num_classes))

        invs = data_dict['inverse_map']
        all_labels = data_dict['targets_mapped']
        _outputs = []
        _targets = []
        for idx in range(int(invs.C[:, -1].max() + 1)):
            cur_scene_pts = (data_dict['lidar'].C[:, -1] == idx).cpu().numpy()
            cur_inv = invs.F[invs.C[:, -1] == idx].cpu().numpy()
            cur_label = (all_labels.C[:, -1] == idx).cpu().numpy()
            outputs_mapped = data_dict['sparse_logits'][cur_scene_pts][cur_inv]
            targets_mapped = all_labels.F[cur_label]
            _outputs.append(outputs_mapped)
            _targets.append(targets_mapped)
        prediction_mapped = torch.cat(_outputs, 0)

        vote_logits.index_add_(0, indices.cpu(), prediction_mapped.cpu())
        prediction = vote_logits.argmax(1)

        if self.ignore_label != 0:
            prediction = prediction[raw_labels != self.ignore_label]
            raw_labels = raw_labels[raw_labels != self.ignore_label]
            prediction += 1
            raw_labels += 1

        if not self.args['submit_to_server']:
            self.val_acc(prediction, raw_labels)
            self.log('val/acc', self.val_acc, on_epoch=True)
            self.val_iou(prediction.cpu().detach().numpy(),
                         raw_labels.cpu().detach().numpy(),
                         )
        else:
            dataset_type = self.args['dataset_params']['pc_dataset_type']
            origin_len_int = self._normalize_origin_len(origin_len)

            if dataset_type == 'WCS2D3D':
                full_label_name = self._build_text_prediction_path(path)
                os.makedirs(os.path.dirname(full_label_name), exist_ok=True)

                if os.path.exists(full_label_name):
                    print('%s already exsist...' % (os.path.basename(full_label_name)))
                else:
                    xyz = self._load_original_xyz_from_path(path, origin_len_int)
                    if xyz is None:
                        xyz = np.zeros((origin_len_int, 3), dtype=np.float32)
                    mapped_prediction = vote_logits[:origin_len_int].argmax(1).cpu().numpy().astype(np.int32)
                    export_label, rgb = self._resolve_export_labels_and_rgb(mapped_prediction)
                    valid_len = min(len(xyz), len(export_label))
                    output_data = np.column_stack([xyz[:valid_len], rgb[:valid_len], export_label[:valid_len]])
                    np.savetxt(full_label_name, output_data, fmt='%.6f %.6f %.6f %.0f %.0f %.0f %d')

            elif dataset_type == 'SemanticKITTI':
                components = self._split_path_components(path)
                sequence = components[-3]
                points_name = components[-1]
                label_name = points_name.replace('bin', 'label')
                full_save_dir = os.path.join(self.submit_dir, 'sequences', sequence, 'predictions')
                os.makedirs(full_save_dir, exist_ok=True)
                full_label_name = os.path.join(full_save_dir, label_name)

                if os.path.exists(full_label_name):
                    print('%s already exsist...' % (label_name))
                    pass

                valid_labels = np.vectorize(self.mapfile['learning_map_inv'].__getitem__)
                original_label = valid_labels(vote_logits.argmax(1).cpu().numpy().astype(int))
                final_preds = original_label.astype(np.uint32)
                final_preds.tofile(full_label_name)

            elif dataset_type != 'nuScenes':
                full_label_name = self._build_text_prediction_path(path)
                os.makedirs(os.path.dirname(full_label_name), exist_ok=True)

                if os.path.exists(full_label_name):
                    print('%s already exsist...' % (os.path.basename(full_label_name)))
                else:
                    xyz = self._load_original_xyz_from_path(path, origin_len_int)
                    if xyz is None:
                        xyz = np.zeros((origin_len_int, 3), dtype=np.float32)
                    mapped_prediction = vote_logits[:origin_len_int].argmax(1).cpu().numpy().astype(np.int32)
                    export_label, rgb = self._resolve_export_labels_and_rgb(mapped_prediction)
                    valid_len = min(len(xyz), len(export_label))
                    output_data = np.column_stack([xyz[:valid_len], rgb[:valid_len], export_label[:valid_len]])
                    np.savetxt(full_label_name, output_data, fmt='%.6f %.6f %.6f %.0f %.0f %.0f %d')

            else:
                meta_dict = {
                    "meta": {
                        "use_camera": False,
                        "use_lidar": True,
                        "use_map": False,
                        "use_radar": False,
                        "use_external": False,
                    }
                }
                os.makedirs(os.path.join(self.submit_dir, 'test'), exist_ok=True)
                with open(os.path.join(self.submit_dir, 'test', 'submission.json'), 'w', encoding='utf-8') as f:
                    json.dump(meta_dict, f)
                original_label = prediction.cpu().numpy().astype(np.uint8)

                assert all((original_label > 0) & (original_label < 17)), \
                    "Error: Array for predictions must be between 1 and 16 (inclusive)."

                full_save_dir = os.path.join(self.submit_dir, 'lidarseg/test')
                full_label_name = os.path.join(full_save_dir, path + '_lidarseg.bin')
                os.makedirs(full_save_dir, exist_ok=True)

                if os.path.exists(full_label_name):
                    print('%s already exsist...' % (full_label_name))
                else:
                    original_label.tofile(full_label_name)

        return data_dict['loss']


    def validation_epoch_end(self, outputs):
        iou, best_miou = self.val_iou.compute()
        finite_iou = iou[np.isfinite(iou)]
        mIoU = float(np.mean(finite_iou)) if finite_iou.size > 0 else 0.0
        str_print = ''
        self.log('val/mIoU', mIoU, on_epoch=True)
        self.log('val/best_miou', best_miou, on_epoch=True)
        str_print += 'Validation per class iou: '

        for class_name, class_iou in zip(self.val_iou.unique_label_str, iou):
            str_print += '\n%s : %.2f%%' % (class_name, class_iou * 100)

        if finite_iou.size == 0:
            str_print += '\n[Warn] All class IoUs are NaN in this validation epoch. Check split/label_mapping/ignore settings.'

        str_print += '\nCurrent val miou is %.3f while the best val miou is %.3f' % (mIoU * 100, best_miou * 100)
        self.print(str_print)


    def test_epoch_end(self, outputs):
        if not self.args['submit_to_server']:
            iou, best_miou = self.val_iou.compute()
            finite_iou = iou[np.isfinite(iou)]
            mIoU = float(np.mean(finite_iou)) if finite_iou.size > 0 else 0.0
            str_print = ''
            self.log('val/mIoU', mIoU, on_epoch=True)
            self.log('val/best_miou', best_miou, on_epoch=True)
            str_print += 'Validation per class iou: '

            for class_name, class_iou in zip(self.val_iou.unique_label_str, iou):
                str_print += '\n%s : %.2f%%' % (class_name, class_iou * 100)

            if finite_iou.size == 0:
                str_print += '\n[Warn] All class IoUs are NaN in this validation epoch. Check split/label_mapping/ignore settings.'

            str_print += '\nCurrent val miou is %.3f while the best val miou is %.3f' % (mIoU * 100, best_miou * 100)
            self.print(str_print)

