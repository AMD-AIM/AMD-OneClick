# AMD ROCm Jupyter Base Image
# Pre-installed with Jupyter Lab for fast startup
FROM docker.io/rocm/vllm-dev:rocm7.1.1_navi_ubuntu24.04_py3.12_pytorch_2.8_vllm_0.10.2rc1

LABEL maintainer="AMD OneClick Team"
LABEL description="AMD ROCm base image with pre-installed Jupyter Lab"

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV SHELL=/bin/bash

# Create working directory
WORKDIR /app

# Install Jupyter and common data science packages
RUN pip install --no-cache-dir \
    jupyter \
    jupyterlab \
    ihighlight \
    ipywidgets \
    matplotlib \
    pandas \
    numpy \
    scipy \
    scikit-learn \
    seaborn \
    plotly \
    tqdm \
    && jupyter lab build --minimize=False 2>/dev/null || true

# Create notebooks directory
RUN mkdir -p /app/notebooks

# Set default working directory for notebooks
WORKDIR /app/notebooks

# Expose Jupyter port
EXPOSE 8888

# Default command - can be overridden
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root"]
