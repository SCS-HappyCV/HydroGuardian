FROM hydro_program3d-env:v1.0

WORKDIR /app

# Keep the base image CUDA/Torch stack intact. Do not install torch/torchvision here.
RUN pip install --no-cache-dir \
    opencv-python-headless==4.9.0.80 \
    matplotlib==3.7.5 \
    thop==0.1.1.post2209072238 \
    scipy==1.10.1 \
    python-multipart==0.0.9

COPY . /app

ENV RFANET_DEVICE=cuda
ENV RFANET_WEIGHTS=/app/weight/best_model.pth

EXPOSE 8011

CMD ["python", "server.py"]
