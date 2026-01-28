#!/bin/bash
# Build script for AMD OneClick PaddleOCR-VL Docker images
#
# Usage:
#   ./docker/build.sh all          # Build all images
#   ./docker/build.sh base         # Build base image only
#   ./docker/build.sh oneclick     # Build oneclick image only  
#   ./docker/build.sh manager      # Build manager image only
#   ./docker/build.sh push         # Push all images to Docker Hub

set -e

# Image names
BASE_IMAGE="vivienfanghua/vllm_paddle:base"
ONECLICK_IMAGE="vivienfanghua/vllm_paddle:ppocr-oneclick"
MANAGER_IMAGE="vivienfanghua/amd-ppocr-vl-manager:latest"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

build_base() {
    echo "=========================================="
    echo "Building Base Image: $BASE_IMAGE"
    echo "=========================================="
    docker build -f docker/Dockerfile.base -t "$BASE_IMAGE" docker/
    echo "✅ Base image built successfully"
}

build_oneclick() {
    echo "=========================================="
    echo "Building OneClick Image: $ONECLICK_IMAGE"
    echo "=========================================="
    docker build -f docker/Dockerfile.ppocr-oneclick -t "$ONECLICK_IMAGE" docker/
    echo "✅ OneClick image built successfully"
}

build_manager() {
    echo "=========================================="
    echo "Building Manager Image: $MANAGER_IMAGE"
    echo "=========================================="
    docker build -f docker/Dockerfile.manager -t "$MANAGER_IMAGE" .
    echo "✅ Manager image built successfully"
}

push_images() {
    echo "=========================================="
    echo "Pushing images to Docker Hub"
    echo "=========================================="
    
    echo "Pushing $BASE_IMAGE..."
    docker push "$BASE_IMAGE"
    
    echo "Pushing $ONECLICK_IMAGE..."
    docker push "$ONECLICK_IMAGE"
    
    echo "Pushing $MANAGER_IMAGE..."
    docker push "$MANAGER_IMAGE"
    
    echo "✅ All images pushed successfully"
}

case "${1:-all}" in
    base)
        build_base
        ;;
    oneclick)
        build_oneclick
        ;;
    manager)
        build_manager
        ;;
    all)
        build_base
        build_oneclick
        build_manager
        ;;
    push)
        push_images
        ;;
    *)
        echo "Usage: $0 {all|base|oneclick|manager|push}"
        echo ""
        echo "Commands:"
        echo "  all       - Build all images (base → oneclick → manager)"
        echo "  base      - Build base image only (Paddle + PaddleX)"
        echo "  oneclick  - Build oneclick image only (requires base)"
        echo "  manager   - Build manager image only"
        echo "  push      - Push all images to Docker Hub"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Docker Images:"
echo "=========================================="
docker images | grep -E "(vllm_paddle|ppocr-vl-manager)" | head -10

