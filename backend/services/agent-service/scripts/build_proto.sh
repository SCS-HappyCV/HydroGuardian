#!/bin/sh
set -e
mkdir -p ./src/generated
rm -f ./src/*_pb2.py ./src/*_pb2_grpc.py
python -m grpc_tools.protoc -I./proto --python_out=./src/generated --grpc_python_out=./src/generated ./proto/case.proto
python -m grpc_tools.protoc -I./proto --python_out=./src/generated --grpc_python_out=./src/generated ./proto/file.proto
python -m grpc_tools.protoc -I./proto --python_out=./src/generated --grpc_python_out=./src/generated ./proto/agent.proto
python - <<'PY'
from pathlib import Path

generated_dir = Path("./src/generated")
for path in generated_dir.glob("*_pb2_grpc.py"):
    text = path.read_text(encoding="utf-8")
    text = text.replace("import agent_pb2 as agent__pb2", "from . import agent_pb2 as agent__pb2")
    text = text.replace("import case_pb2 as case__pb2", "from . import case_pb2 as case__pb2")
    text = text.replace("import file_pb2 as file__pb2", "from . import file_pb2 as file__pb2")
    path.write_text(text, encoding="utf-8")
PY
