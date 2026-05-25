#!/bin/sh
set -e
python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/case.proto
python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/file.proto
python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/agent.proto
