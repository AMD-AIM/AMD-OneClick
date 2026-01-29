#!/bin/bash
# AMD OneClick Space Entrypoint Script
# This script handles the startup of Space instances

set -e

echo "=============================================="
echo "AMD OneClick Space Instance Starting"
echo "=============================================="
echo "Space ID: ${SPACE_ID:-unknown}"
echo "Repository: ${REPO_URL:-unknown}"
echo "Branch: ${REPO_BRANCH:-main}"
echo "Start Command: ${START_COMMAND:-not specified}"
echo "Exposed Port: ${EXPOSED_PORT:-7860}"
echo "=============================================="

# Create workspace directory
WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace}"
mkdir -p "${WORKSPACE_DIR}"
cd "${WORKSPACE_DIR}"

# Clone the repository if URL is provided
if [ -n "${REPO_URL}" ]; then
    echo ""
    echo "=== Cloning Repository ==="
    BRANCH="${REPO_BRANCH:-main}"
    
    # Check if it's a private repo (credentials in URL)
    if [[ "${REPO_URL}" == *"@"* ]]; then
        echo "Cloning private repository..."
    else
        echo "Cloning public repository..."
    fi
    
    # Clone with depth 1 for faster startup
    if git clone --depth 1 -b "${BRANCH}" "${REPO_URL}" app 2>&1; then
        echo "Repository cloned successfully"
        cd app
    else
        echo "Warning: Failed to clone repository, continuing anyway..."
        mkdir -p app
        cd app
    fi
else
    echo "No repository URL provided, using empty workspace"
    mkdir -p app
    cd app
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

# Install requirements if exists
if [ -f "requirements.txt" ]; then
    echo ""
    echo "=== Installing Requirements ==="
    pip install --no-cache-dir -r requirements.txt 2>&1 || echo "Warning: Some requirements failed to install"
fi

# Install setup.py if exists
if [ -f "setup.py" ]; then
    echo ""
    echo "=== Installing Package ==="
    pip install --no-cache-dir -e . 2>&1 || echo "Warning: Package installation failed"
fi

# Check for app.py (Gradio/Streamlit convention)
if [ -z "${START_COMMAND}" ]; then
    if [ -f "app.py" ]; then
        echo "Found app.py, auto-detecting framework..."
        if grep -q "gradio" app.py 2>/dev/null; then
            START_COMMAND="python app.py"
        elif grep -q "streamlit" app.py 2>/dev/null; then
            START_COMMAND="streamlit run app.py --server.port=${EXPOSED_PORT:-7860} --server.address=0.0.0.0"
        else
            START_COMMAND="python app.py"
        fi
    elif [ -f "main.py" ]; then
        START_COMMAND="python main.py"
    fi
fi

# Verify start command is set
if [ -z "${START_COMMAND}" ]; then
    echo "Error: No start command specified and no app.py/main.py found"
    echo "Please set START_COMMAND environment variable"
    exit 1
fi

# Set up signal handling for graceful shutdown
cleanup() {
    echo ""
    echo "Received shutdown signal, cleaning up..."
    kill -TERM "$child_pid" 2>/dev/null
    wait "$child_pid"
    exit 0
}
trap cleanup SIGTERM SIGINT

echo ""
echo "=== Starting Application ==="
echo "Command: ${START_COMMAND}"
echo "Working Directory: $(pwd)"
echo ""

# Execute the start command
exec ${START_COMMAND}

