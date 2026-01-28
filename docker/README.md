# PaddleOCR-VL Docker Images

本目录包含 PaddleOCR-VL OneClick 服务的所有 Docker 镜像构建文件。

## 镜像层级

```
┌─────────────────────────────────────────────────────────────────┐
│  rocm/vllm-dev:nightly_main_20260125  (ROCm 7.0 + vLLM)        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  vivienfanghua/vllm_paddle:base  (~26GB)                       │
│  Dockerfile.base                                                │
│  ─────────────────────────────────────────────────────────────  │
│  + PaddlePaddle DCU (ROCm 7.0)                                  │
│  + PaddleX + OCR 依赖                                           │
│  + 配置文件                                                      │
│  - 无 entrypoint (通用基础镜像)                                   │
│  - 无模型文件                                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  vivienfanghua/vllm_paddle:ppocr-oneclick  (~38GB)             │
│  Dockerfile.ppocr-oneclick                                      │
│  ─────────────────────────────────────────────────────────────  │
│  + Jupyter Lab                                                  │
│  + 模型文件 (checkpoint-5000, layout_0116)                       │
│  + oneclick_entrypoint.sh                                       │
│  用于 K8s OneClick 服务                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  vivienfanghua/amd-ppocr-vl-manager:latest  (~209MB)           │
│  Dockerfile.manager                                             │
│  ─────────────────────────────────────────────────────────────  │
│  FROM python:3.12-slim                                          │
│  + FastAPI + K8s 客户端                                          │
│  OneClick 管理服务                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 构建镜像

### 使用构建脚本

```bash
# 构建所有镜像
./docker/build.sh all

# 只构建基础镜像
./docker/build.sh base

# 只构建 OneClick 镜像 (需要先构建 base)
./docker/build.sh oneclick

# 只构建 Manager 镜像
./docker/build.sh manager

# 推送所有镜像到 Docker Hub
./docker/build.sh push
```

### 手动构建

```bash
cd /path/to/AMD-OneClick

# 1. 构建基础镜像
docker build -f docker/Dockerfile.base -t vivienfanghua/vllm_paddle:base docker/

# 2. 构建 OneClick 镜像
docker build -f docker/Dockerfile.ppocr-oneclick -t vivienfanghua/vllm_paddle:ppocr-oneclick docker/

# 3. 构建 Manager 镜像
docker build -f docker/Dockerfile.manager -t vivienfanghua/amd-ppocr-vl-manager:latest .
```

## 目录结构

```
docker/
├── Dockerfile.base           # 基础镜像 (Paddle + PaddleX)
├── Dockerfile.ppocr-oneclick # OneClick 镜像 (+ Jupyter + 模型)
├── Dockerfile.manager        # Manager 服务镜像
├── build.sh                  # 构建脚本
├── models/                   # 预下载的模型文件
│   ├── checkpoint-5000/      # PaddleOCR-VL 模型
│   └── layout_0116/          # Layout 检测模型
├── paddlepaddle_dcu-*.whl    # PaddlePaddle DCU wheel
└── README.md                 # 本文档
```

## 环境变量

### OneClick 镜像 (`ppocr-oneclick`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GPU_MEMORY_UTILIZATION` | `0.85` | GPU 显存使用比例 |
| `VLLM_PORT` | `8118` | vLLM 服务端口 |
| `JUPYTER_PORT` | `8888` | Jupyter Lab 端口 |
| `NOTEBOOK_TOKEN` | `amd-oneclick` | Jupyter 访问 token |
| `NOTEBOOK_URL` | - | 自动下载的 notebook URL |
| `INSTANCE_ID` | - | K8s 实例 ID (用于 Nginx 代理) |

## 本地运行

```bash
# 运行 OneClick 镜像 (需要 AMD GPU)
docker run -it --rm \
  -p 8888:8888 \
  -p 8118:8118 \
  --device /dev/kfd \
  --device /dev/dri \
  --group-add video \
  -e GPU_MEMORY_UTILIZATION=0.85 \
  vivienfanghua/vllm_paddle:ppocr-oneclick

# 访问 Jupyter Lab: http://localhost:8888/?token=amd-oneclick
```

## K8s 部署

请参考 `k8s-ppocr-deployment.yaml` 和 `nginx-proxy.yaml`。

