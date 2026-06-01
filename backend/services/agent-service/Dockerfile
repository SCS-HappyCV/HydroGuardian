FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY proto ./proto
COPY scripts ./scripts
COPY src ./src
RUN chmod +x ./scripts/build_proto.sh && ./scripts/build_proto.sh
EXPOSE 9091
CMD ["python", "-u", "src/main.py"]
