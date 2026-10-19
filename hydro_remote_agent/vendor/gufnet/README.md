# GUFNet inference snapshot

This directory vendors the GUFNet source required by HydroRemoteAgent inference.

- Source: `/opt/acmf-lgc-zmap`
- Snapshot purpose: load the trained `model_3d` branch without a runtime dependency on the source repository
- Checkpoint files are deployment assets stored in `../../checkpoints/gufnet`
- The original source files are kept unchanged except for package-level integration outside this directory

GUFNet was trained with image and point-cloud supervision. Its evaluation path uses the point-cloud branch only, so both segmentation adapters share the same `model_3d` inference engine.
