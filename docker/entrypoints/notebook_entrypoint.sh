#!/bin/bash
# AMD OneClick Generic Notebook Entrypoint Script
# This script handles the startup of generic Notebook instances

set -e

echo "=============================================="
echo "AMD OneClick Notebook Instance Starting"
echo "=============================================="
echo "Instance ID: ${INSTANCE_ID:-unknown}"
echo "Notebook URL: ${NOTEBOOK_URL:-none}"
echo "Jupyter Port: ${JUPYTER_PORT:-8888}"
echo "=============================================="

# Create workspace directory
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
NOTEBOOK_DIR="${NOTEBOOK_DIR:-${WORKSPACE_DIR}/notebooks}"
mkdir -p "${NOTEBOOK_DIR}"

# Download notebook if URL provided
if [ -n "${NOTEBOOK_URL}" ]; then
    echo ""
    echo "=== Downloading Notebook ==="
    cd "${NOTEBOOK_DIR}"
    
    # Extract filename from URL
    NOTEBOOK_FILE=$(basename "${NOTEBOOK_URL}")
    
    # Handle GitHub URLs
    if [[ "${NOTEBOOK_URL}" == *"github.com"* ]] && [[ "${NOTEBOOK_URL}" != *"raw.githubusercontent.com"* ]]; then
        # Convert to raw URL
        NOTEBOOK_URL=$(echo "${NOTEBOOK_URL}" | sed 's|github.com|raw.githubusercontent.com|' | sed 's|/blob/|/|')
        echo "Converted to raw URL: ${NOTEBOOK_URL}"
    fi
    
    echo "Downloading: ${NOTEBOOK_URL}"
    if wget -q --show-progress -O "${NOTEBOOK_FILE}" "${NOTEBOOK_URL}"; then
        echo "Notebook downloaded: ${NOTEBOOK_FILE}"
    else
        echo "Warning: Failed to download notebook, creating empty workspace"
    fi
fi

# Clone repository if REPO_URL is provided (for notebook repositories)
if [ -n "${REPO_URL}" ]; then
    echo ""
    echo "=== Cloning Repository ==="
    BRANCH="${REPO_BRANCH:-main}"
    
    cd "${WORKSPACE_DIR}"
    if git clone --depth 1 -b "${BRANCH}" "${REPO_URL}" repo 2>&1; then
        echo "Repository cloned successfully"
        # If notebook path is specified, copy to notebook dir
        if [ -n "${NOTEBOOK_PATH}" ] && [ -f "repo/${NOTEBOOK_PATH}" ]; then
            cp "repo/${NOTEBOOK_PATH}" "${NOTEBOOK_DIR}/"
            echo "Copied notebook from repository"
        fi
    else
        echo "Warning: Failed to clone repository"
    fi
fi

# Download and setup Conda environment if specified
if [ -n "${CONDA_ENV_URL}" ] && [ -n "${CONDA_ENV}" ]; then
    echo ""
    echo "=== Setting up Conda Environment ==="
    echo "Environment: ${CONDA_ENV}"
    echo "URL: ${CONDA_ENV_URL}"
    
    CONDA_DIR="/opt/conda_envs/${CONDA_ENV}"
    
    if [ ! -d "${CONDA_DIR}" ]; then
        mkdir -p /opt/conda_envs
        echo "Downloading conda environment..."
        
        if wget -q --show-progress -O /tmp/conda_env.tar.gz "${CONDA_ENV_URL}"; then
            echo "Extracting conda environment..."
            tar -xzf /tmp/conda_env.tar.gz -C /opt/conda_envs
            rm -f /tmp/conda_env.tar.gz
            echo "Conda environment installed"
        else
            echo "Warning: Failed to download conda environment"
        fi
    fi
    
    if [ -d "${CONDA_DIR}" ]; then
        export PATH="${CONDA_DIR}/bin:${PATH}"
        echo "Conda environment ${CONDA_ENV} activated"
        python --version 2>/dev/null || echo "Python not found in conda env"
    fi
fi

# Install requirements if exists in workspace
if [ -f "${WORKSPACE_DIR}/requirements.txt" ]; then
    echo ""
    echo "=== Installing Requirements ==="
    pip install --no-cache-dir -r "${WORKSPACE_DIR}/requirements.txt" 2>&1 || echo "Warning: Some requirements failed to install"
fi

# Ensure jupyter is installed
if ! command -v jupyter &> /dev/null; then
    echo ""
    echo "=== Installing Jupyter ==="
    pip install --no-cache-dir jupyterlab jupyter 2>&1
fi

# Determine base URL based on instance ID
if [ -n "${INSTANCE_ID}" ]; then
    BASE_URL="/instance/${INSTANCE_ID}/"
    echo ""
    echo "=== Jupyter Configuration ==="
    echo "Base URL: ${BASE_URL}"
else
    BASE_URL="/"
fi

# Set up signal handling for graceful shutdown
cleanup() {
    echo ""
    echo "Received shutdown signal, shutting down Jupyter..."
    kill -TERM "$child_pid" 2>/dev/null
    wait "$child_pid"
    exit 0
}
trap cleanup SIGTERM SIGINT

echo ""
echo "=== Starting Jupyter Lab ==="
echo "Notebook Directory: ${NOTEBOOK_DIR}"
echo "Port: ${JUPYTER_PORT:-8888}"
echo "Token: ${NOTEBOOK_TOKEN:-amd-oneclick}"
echo ""

# Start Jupyter Lab
exec jupyter lab \
    --ip=0.0.0.0 \
    --port="${JUPYTER_PORT:-8888}" \
    --no-browser \
    --allow-root \
    --ServerApp.token="${NOTEBOOK_TOKEN:-amd-oneclick}" \
    --ServerApp.base_url="${BASE_URL}" \
    --notebook-dir="${NOTEBOOK_DIR}"

