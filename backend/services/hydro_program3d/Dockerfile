FROM crpi-vv5mnklpv7fjti91.cn-guangzhou.personal.cr.aliyuncs.com/ilotus-dockerhub/hydro_program3d:v1.0

WORKDIR /app

RUN mkdir -p /app/data /app/checkpoints

COPY web /app/web
COPY algorithm /app/algorithm
COPY requirements.txt /app/requirements.txt

EXPOSE 8093

ENV HYDRO_PROGRAM3D_HOST=0.0.0.0
ENV HYDRO_PROGRAM3D_PORT=8093

CMD ["python", "-m", "web.main"]
