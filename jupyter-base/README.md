# AMD ROCm Jupyter Base Image

This directory contains the Dockerfile to build an AMD ROCm base image with pre-installed Jupyter Lab for fast startup.

## Build Instructions

```bash
# Build the image
docker build -t vivienfanghua/amd-jupyter:latest .

# Push to Docker Hub
docker push vivienfanghua/amd-jupyter:latest
```

## Included Packages

- **Jupyter Lab** - Interactive development environment
- **ihighlight** - Syntax highlighting for notebooks
- **ipywidgets** - Interactive widgets
- **matplotlib** - Plotting library
- **pandas** - Data manipulation
- **numpy** - Numerical computing
- **scipy** - Scientific computing
- **scikit-learn** - Machine learning
- **seaborn** - Statistical visualization
- **plotly** - Interactive plots
- **tqdm** - Progress bars

## Base Image

Based on: `rocm/vllm-dev:rocm7.1.1_navi_ubuntu24.04_py3.12_pytorch_2.8_vllm_0.10.2rc1`

This includes:
- ROCm 7.1.1
- PyTorch 2.8
- vLLM 0.10.2rc1
- Python 3.12
- Ubuntu 24.04
