# RFANet Inference API

## Run

From the repository root:

```bash
python -m uvicorn server:app --app-dir Api --host172.16.224.4  --port 8011
```

Optional environment variables:

- RFANET_WEIGHTS: path to a .pth file (default: Api/weight/best_model.pth)
- RFANET_DEVICE: cuda or cpu (default: auto)

## API Example

### Health Check

```bash
curl http://172.16.224.4:8011/health
```

### Predict

```bash
curl -X POST "http:/172.16.224.4:8011/predict" \
  -F "pre_image=@/absolute/path/to/pre.png" \
  -F "post_image=@/absolute/path/to/post.png" \
  -F "threshold=0.5" \
  -o mask.png
```
