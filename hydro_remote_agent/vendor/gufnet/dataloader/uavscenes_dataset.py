"""
UAVScenes Dataset Loader
ICCV 2025 - Multi-Modal UAV Dataset
"""
import os
import glob
import yaml
import numpy as np
import cv2

from PIL import Image
from torch.utils import data

# 导入注册函数
from dataloader.pc_dataset import register_dataset


# ============== Camera-LiDAR Calibration (from calibration_results.py) ==============
CALIBRATION_DICT = {
    'AMtown': {
        'K': np.array([1453.72, 0.0, 1172.18, 
                       0.0, 1453.28, 1041.78, 
                       0.0, 0.0, 1.0]).reshape(3, 3),
        'dist': np.array([-0.121, 0.1113, 0.0016, 0.00013, -0.062353]),
        'R': np.array([0.00298088, -0.999728, -0.0231416, 
                       -0.00504636, 0.0231263, -0.99972, 
                       0.999983, 0.00309683, -0.00497605]).reshape(3, 3),
        't': np.array([0.0025563, 0.0567484, -0.0512149])
    },
    'AMvalley': {
        'K': np.array([1453.88, 0.0, 1182.53, 
                       0.0, 1452.85, 1045.82, 
                       0.0, 0.0, 1.0]).reshape(3, 3),
        'dist': np.array([-0.052, 0.1168, 0.0015, 0.00013, -0.068564]),
        'R': np.array([0.00298068, -0.999735, -0.0231428, 
                       -0.00504595, 0.023132, -0.99974, 
                       0.999985, 0.00309701, -0.00497598]).reshape(3, 3),
        't': np.array([-0.0025563, 0.0567484, -0.0512149])
    },
    'HKairport': {
        'K': np.array([1451.28, 0.0, 1177.5, 
                       0.0, 1451.29, 1043.5, 
                       0.0, 0.0, 1.0]).reshape(3, 3),
        'dist': np.array([-0.0572, 0.1209, 0.00124, -0.00018, -0.06327]),
        'R': np.array([0.00322743, -0.999736, -0.022768, 
                       -0.0560389, 0.0227496, -0.999725, 
                       0.999979, 0.00335414, -0.00552898]).reshape(3, 3),
        't': np.array([0.00242461, 0.0765454, -0.0313375])
    },
    'HKisland': {
        'K': np.array([1444.43, 0.0, 1177.8, 
                       0.0, 1444.34, 1043.6, 
                       0.0, 0.0, 1.0]).reshape(3, 3),
        'dist': np.array([-0.053, 0.121, 0.00127, 0.00043, -0.06495]),
        'R': np.array([0.00352762, -0.999765, -0.0213775, 
                       -0.0111803, 0.0213369, -0.99971, 
                       0.999931, 0.00376561, -0.0111025]).reshape(3, 3),
        't': np.array([-0.0025563, 0.0470454, -0.0513375])
    },
    'HK_GNSS': {
        'K': np.array([1444.43, 0.0, 1179.50,
                       0.0, 1444.34, 1044.90,
                       0.0, 0.0, 1.0]).reshape(3, 3),
        'dist': np.array([-0.0560, 0.1180, 0.00122, 0.00064, -0.0627]),
        'R': np.array([0.00363212, -0.999819, -0.0213618,
                       -0.0111679, 0.0214512, -0.999591,
                       0.999879, 0.00375613, -0.0111134]).reshape(3, 3),
        't': np.array([-0.0021928, 0.0470312, -0.0513126])
    }
}


def get_calibration(scene_name):
    """根据场景名获取对应的校准参数"""
    if 'AMtown' in scene_name:
        return CALIBRATION_DICT['AMtown']
    elif 'AMvalley' in scene_name:
        return CALIBRATION_DICT['AMvalley']
    elif 'HKairport' in scene_name:
        if 'GNSS' in scene_name:
            return CALIBRATION_DICT['HK_GNSS']
        return CALIBRATION_DICT['HKairport']
    elif 'HKisland' in scene_name:
        if 'GNSS' in scene_name:
            return CALIBRATION_DICT['HK_GNSS']
        return CALIBRATION_DICT['HKisland']
    else:
        # 默认使用 AMtown 的参数
        print(f"[Warning] Unknown scene: {scene_name}, using AMtown calibration")
        return CALIBRATION_DICT['AMtown']


@register_dataset
class UAVScenes(data.Dataset):
    """
    UAVScenes Dataset Loader
    
    数据结构:
    - interval5_CAM_LIDAR/
        - interval5_AMtown01/
            - sampleinfos_interpolated.json
            - interval5_CAM/  (图像)
            - interval5_LIDAR/  (点云 .txt: x y z)
    - interval5_LIDAR_label/
        - interval5_AMtown01/
            - interval5_LIDAR_label_id/  (标签 .txt: 每行一个ID)
    """
    
    def __init__(self, config, data_path, imageset='train', num_vote=1):
        with open(config['dataset_params']['label_mapping'], 'r', encoding='utf-8') as stream:
            label_yaml = yaml.safe_load(stream)
        
        self.config = config
        self.num_vote = num_vote
        self.learning_map = label_yaml['learning_map']
        self.imageset = imageset
        self.data_path = data_path
        
        # 获取数据划分
        if imageset == 'train':
            split = label_yaml['split']['train']
            if config['train_params'].get('trainval', False):
                split += label_yaml['split']['valid']
        elif imageset == 'val':
            split = label_yaml['split']['valid']
        elif imageset == 'test':
            split = label_yaml['split']['test']
        else:
            raise Exception('Split must be train/val/test')
        
        # 收集文件列表
        self.files = []
        self._collect_files(split)
        
        # 类别权重 (如果配置中有的话)
        if 'seg_labelweights' in config['dataset_params']:
            seg_num_per_class = np.array(config['dataset_params']['seg_labelweights'])
            seg_labelweights = seg_num_per_class / np.sum(seg_num_per_class)
            self.seg_labelweights = np.power(np.amax(seg_labelweights) / seg_labelweights, 1 / 3.0)
        else:
            self.seg_labelweights = np.ones(18)  # 18个有效类别
    
    def _collect_files(self, split):
        """收集所有数据文件路径"""
        lidar_root = os.path.join(self.data_path, "interval5_CAM_LIDAR")
        label_root = os.path.join(self.data_path, "interval5_LIDAR_label")
        
        for scene in split:
            scene_lidar_dir = os.path.join(lidar_root, scene, "interval5_LIDAR")
            scene_label_dir = os.path.join(label_root, scene, "interval5_LIDAR_label_id")
            scene_image_dir = os.path.join(lidar_root, scene, "interval5_CAM")
            
            if not os.path.exists(scene_lidar_dir):
                print(f"[Warning] Scene dir not found: {scene_lidar_dir}, skipping.")
                continue
            
            # 获取所有点云文件
            lidar_files = sorted(glob.glob(os.path.join(scene_lidar_dir, "*.txt")))
            
            for lf in lidar_files:
                filename = os.path.basename(lf)
                
                # 构造标签路径
                label_path = os.path.join(scene_label_dir, filename)
                
                # 构造图像路径
                # Filename format: image{T1}_lidar{T2}.txt -> {T1}.jpg
                try:
                    img_time = filename.split('_')[0].replace('image', '')  # 1658137057.641204937
                    img_filename = img_time + ".jpg"
                    image_path = os.path.join(scene_image_dir, img_filename)
                except Exception as e:
                    print(f"[Warning] Skipping malformed filename: {filename}, error: {e}")
                    continue
                
                # 验证文件存在
                if os.path.exists(label_path) and os.path.exists(image_path):
                    for _ in range(self.num_vote):
                        self.files.append({
                            "lidar_path": lf,
                            "label_path": label_path,
                            "image_path": image_path,
                            "scene_name": scene,
                            "name": filename
                        })
                else:
                    if not os.path.exists(label_path):
                        print(f"[Warning] Label not found: {label_path}")
                    if not os.path.exists(image_path):
                        print(f"[Warning] Image not found: {image_path}")
        
        print(f"[{self.imageset}] Collected {len(self.files)} samples from {len(split)} scenes.")
    
    def __len__(self):
        return len(self.files)
    
    def __getitem__(self, index):
        item = self.files[index]
        
        # 1. 加载点云 (x y z, 空格分隔)
        points = np.loadtxt(item['lidar_path'], dtype=np.float32)
        origin_len = len(points)
        
        # 2. 加载标签
        if self.imageset == 'test':
            labels = np.zeros((origin_len, 1), dtype=np.int32)
        else:
            labels = np.loadtxt(item['label_path'], dtype=np.int32).reshape(-1, 1)
            # 应用 learning_map
            labels = np.vectorize(self.learning_map.get)(labels)
        
        # 3. 加载图像
        image = Image.open(item['image_path']).convert('RGB')
        image_np = np.array(image)  # H x W x 3
        
        # 4. 获取投影矩阵和校准参数
        calib = get_calibration(item['scene_name'])
        proj_matrix = self._compute_projection_matrix(calib, image.size)
        
        # 5. 投影点云到图像，采样 RGB 颜色
        xyz = points[:, :3]
        points_hcoords = np.concatenate([xyz, np.ones((origin_len, 1), dtype=np.float32)], axis=1)
        img_points = (proj_matrix @ points_hcoords.T).T
        depth = img_points[:, 2]
        img_points = img_points[:, :2] / np.expand_dims(depth + 1e-8, axis=1)
        
        # 判断哪些点在图像视野内
        img_h, img_w = image_np.shape[:2]
        u = img_points[:, 0].astype(np.int32)
        v = img_points[:, 1].astype(np.int32)
        
        # 有效点：在图像范围内且深度为正（在相机前方）
        valid_mask = (u >= 0) & (u < img_w) & (v >= 0) & (v < img_h) & (depth > 0)
        
        # 初始化 RGB 为默认灰色（视野外的点）
        rgb = np.ones((origin_len, 3), dtype=np.float32) * 0.5
        
        # 对视野内的点从图像采样真实 RGB
        rgb[valid_mask] = image_np[v[valid_mask], u[valid_mask], :].astype(np.float32) / 255.0
        
        # 构造返回数据
        data_dict = {}
        data_dict['xyz'] = xyz
        data_dict['labels'] = labels.astype(np.uint8)
        data_dict['instance_label'] = labels.astype(np.uint8)
        data_dict['rgb'] = rgb  # 从图像采样的 RGB 颜色
        data_dict['origin_len'] = origin_len
        data_dict['img'] = image
        data_dict['proj_matrix'] = proj_matrix
        
        return data_dict, item['lidar_path']
    
    def _compute_projection_matrix(self, calib, img_size):
        """
        计算 LiDAR -> Image 的投影矩阵
        
        投影流程:
        1. P_cam = R @ P_lidar + t   (LiDAR坐标系 -> Camera坐标系)
        2. p_img = K @ P_cam         (Camera坐标系 -> 图像像素坐标)
        
        合并为 3x4 矩阵: P = K @ [R | t]
        """
        K = calib['K']
        R = calib['R']
        t = calib['t'].reshape(3, 1)
        
        # 构造 [R | t] (3x4)
        Rt = np.hstack([R, t])
        
        # P = K @ [R | t] (3x4)
        proj_matrix = K @ Rt
        
        return proj_matrix.astype(np.float32)


def get_UAVScenes_label_name(label_mapping):
    """获取 UAVScenes 的类别名称映射"""
    with open(label_mapping, 'r', encoding='utf-8') as stream:
        yaml_data = yaml.safe_load(stream)
    
    label_name = {}
    for orig_id, train_id in yaml_data['learning_map'].items():
        if train_id != 255:
            label_name[train_id] = yaml_data['labels'][orig_id]
    
    return label_name
