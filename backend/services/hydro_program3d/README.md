# hydro_program3d 服务

这是本地 `hydro_program3d` 算法和证据编译器的 FastAPI 封装。服务代码、算法代码、数据目录和 checkpoint 目录都放在当前目录下，不依赖外部源码路径。

## 目录结构

```text
hydro_program3d/
|- web/                 # FastAPI 服务代码
|- algorithm/           # 本地算法源码
|- data/                # 可选的数据暂存目录
|- checkpoints/         # /execute 加载的模型 checkpoint
|- requirements.txt
|- Dockerfile
`- README.md
```

## 本地运行

```bash
cd backend/services/hydro_program3d
pip install -r requirements.txt
python -m web.main
```

默认监听地址是 `0.0.0.0:8093`。

如果需要，可以在启动前覆盖：

```powershell
$env:HYDRO_PROGRAM3D_HOST="0.0.0.0"
$env:HYDRO_PROGRAM3D_PORT="8093"
python -m web.main
```

## 运行注意事项

### 1. checkpoint 放置位置

模型 checkpoint 放在 `./checkpoints/` 目录下，例如：

```text
checkpoints/
`- hydro_program3d_demo.pth
```

`/execute` 支持以下写法：

- `"checkpoint_name": "hydro_program3d_demo"`
- `"checkpoint_name": "hydro_program3d_demo.pth"`
- 如果文件在 `checkpoints/subdir/` 下，也可以写 `"checkpoint_name": "subdir/hydro_program3d_demo.pth"`

当不带后缀时，加载器会自动尝试 `.pt`、`.pth` 和 `.bin`。

如果省略 `checkpoint_name`，服务会只根据 `model_overrides` 实例化模型。这种模式适合接口联调和冒烟测试，不适合真实推理，因为没有加载训练权重。

### 2. 依赖约束

当前 `requirements.txt` 已包含 Web 服务依赖和 `open-clip-torch`，足以支持：

- `GET /health`
- `POST /compile_evidence`
- 使用 `text_encoder_type=clip` 的文本编码

如果你的 checkpoint 使用了稀疏点云骨干，请在镜像中补齐对应依赖：

- `point_encoder_type=spconv`：需要 `spconv` 和 `torch_scatter`，并且只能在 CUDA 上运行
- `point_encoder_type=openscene`：需要 OpenScene 相关依赖栈
- `text_encoder_type=clip`：需要匹配的 CLIP 权重目录

使用 `point_encoder_type=spconv` 时，容器必须用 GPU 模式启动：

```bash
docker run --gpus all ...
```

对应的 `/execute` 请求也必须使用：

```json
"device": "cuda"
```

对于 `text_encoder_type=clip`，服务会优先在以下位置自动查找 CLIP 权重：

- `checkpoints/clip/`
- `checkpoints/clip_weights/`
- `checkpoints/open_clip/`
- `checkpoint` 文件同目录
- `checkpoint` 同名目录，例如 `checkpoints/<checkpoint_stem>/clip/`

权重目录中至少需要存在以下文件之一：

- `open_clip_pytorch_model.bin`
- `pytorch_model.bin`
- `open_clip_model.safetensors`

### 3. 输入数据要求

`/execute` 不会自动从 `data/` 目录读取原始文件。调用方需要把预处理后的张量以 JSON 形式传进来。

`sample` 必填字段：

- `images`：`[3, H, W]` 或 `[B, 3, H, W]`
- `points_xyz`：`[N, 3]` 或 `[B, N, 3]`
- `points_rgb`：`[N, 3]` 或 `[B, N, 3]`
- `point_geometry_features`：`[N, G]` 或 `[B, N, G]`

可选字段：

- `valid_point_mask`：`[N]` 或 `[B, N]`

另外还必须至少提供以下其中一项：

- `program`
- `program_bundle`
- `sample.text`
- `sample.texts`

下面的 JSON 仅用于说明接口字段结构。真实请求应当来自你的数据预处理流水线，而不是手写的 toy 数组。

## 接口

- `GET /health`
- `POST /execute`
- `POST /compile_evidence`
- `POST /compile_evidence_batch`

## 请求示例

### `GET /health`

这个接口没有请求体。

```bash
curl http://127.0.0.1:8093/health
```

典型返回字段：

- `service_root`
- `algorithm_dir`
- `data_dir`
- `checkpoint_dir`
- `compiler_available`
- `compiler_error`

### `POST /execute`

下面是一个 field schema program 的最小示例。label id 取值遵循 `algorithm/wcs_unified/dataset.py`，其中 `waterline=12`，`ditch=13`。这里默认使用 `spconv + clip` 配置。

```json
{
  "checkpoint_name": "hydro_program3d_demo.pth",
  "device": "cuda",
  "model_overrides": {
    "point_encoder_type": "spconv",
    "text_encoder_type": "clip",
    "clip_model_name": "ViT-B-32",
    "use_ortho_prior": true,
    "use_program_executor": true,
    "program_schema_mode": "field",
    "program_version": "v1_field"
  },
  "sample": {
    "sample_id": "demo-001",
    "text": "segment waterline near ditch",
    "images": [
      [[0.00, 0.10], [0.20, 0.30]],
      [[0.00, 0.10], [0.20, 0.30]],
      [[0.00, 0.10], [0.20, 0.30]]
    ],
    "points_xyz": [
      [0.0, 0.0, 0.0],
      [1.0, 0.0, 0.0],
      [1.0, 1.0, 0.1],
      [0.0, 1.0, 0.1]
    ],
    "points_rgb": [
      [0.20, 0.30, 0.40],
      [0.21, 0.32, 0.41],
      [0.19, 0.28, 0.39],
      [0.18, 0.27, 0.38]
    ],
    "point_geometry_features": [
      [0.10, 0.00, 0.20, 0.80],
      [0.09, 0.01, 0.21, 0.78],
      [0.12, 0.02, 0.22, 0.77],
      [0.11, 0.01, 0.19, 0.79]
    ],
    "valid_point_mask": [true, true, true, true]
  },
  "program": {
    "program_schema_mode": "field",
    "program_version": "v1_field",
    "target": "waterline",
    "target_label_ids": [12],
    "attributes": ["thin", "linear"],
    "relations": [
      {
        "type": "near",
        "reference": "ditch",
        "reference_label_ids": [13],
        "distance_m": 5.0,
        "margin_m": null,
        "evidence": ["geometry"]
      }
    ],
    "negatives": ["cement road"],
    "negative_label_ids": [2],
    "evidence": ["geometry", "ortho_edge"],
    "metadata": {},
    "source_text": "segment waterline near ditch"
  }
}
```

重点关注返回中的：

- `execution_result.outputs`：原始模型和程序执行输出
- `execution_result.model_config`：实际解析后的运行配置
- `checkpoint_path`：最终解析到的 checkpoint 文件路径

### `POST /compile_evidence`

推荐做法是回传同一个 `sample`，并且在以下三种输入里任选一种：

1. 直接传 `POST /execute` 的完整响应体
2. 传里面的 `execution_result`
3. 只传 `outputs`

下面示例使用的是直接传 `outputs`：

```json
{
  "sample": {
    "sample_id": "demo-001",
    "text": "segment waterline near ditch",
    "points_xyz": [
      [0.0, 0.0, 0.0],
      [1.0, 0.0, 0.0],
      [1.0, 1.0, 0.1],
      [0.0, 1.0, 0.1]
    ],
    "valid_point_mask": [true, true, true, true],
    "program": {
      "program_schema_mode": "field",
      "program_version": "v1_field",
      "target": "waterline",
      "target_label_ids": [12],
      "attributes": ["thin", "linear"],
      "relations": [
        {
          "type": "near",
          "reference": "ditch",
          "reference_label_ids": [13],
          "distance_m": 5.0,
          "margin_m": null,
          "evidence": ["geometry"]
        }
      ],
      "negatives": ["cement road"],
      "negative_label_ids": [2],
      "evidence": ["geometry", "ortho_edge"],
      "metadata": {},
      "source_text": "segment waterline near ditch"
    }
  },
  "outputs": {
    "selected_program_mask": [[0.02, 0.81, 0.93, 0.05]],
    "selected_candidate_idx": [0],
    "candidate_scores": [[2.10, -0.30]],
    "candidate_posterior_scores": [[0.88, 0.12]],
    "selected_verifier_score": [0.91],
    "posterior_no_target_mass": [0.04],
    "abstain_logits": [-2.20]
  },
  "batch_index": 0
}
```

重点关注返回中的：

- `evidence_pack.candidate_regions`
- `evidence_pack.confidence`
- `evidence_pack.review_required`
- `evidence_pack.raw_trace`

### `POST /compile_evidence_batch`

批量编译是可选的。它接收一个 batch 形式的 `sample` 和对应的 batch `outputs`，适合一个 `/execute` 调用一次返回多个样本的场景。

## Docker

构建镜像：

```bash
docker build -t hydro-program3d-service .
```

运行容器：

```bash
docker run --rm -p 8093:8093 hydro-program3d-service
```

如果希望容器读取本地 checkpoint 或暂存数据，可以把 `./checkpoints` 和 `./data` 挂载到容器内的 `/app/checkpoints` 和 `/app/data`。
