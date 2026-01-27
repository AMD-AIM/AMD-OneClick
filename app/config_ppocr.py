"""
Configuration settings for AMD OneClick PaddleOCR-VL Manager
"""
import os
from typing import Optional


class Settings:
    # K8s Configuration
    K8S_NAMESPACE: str = os.getenv("K8S_NAMESPACE", "default")
    
    # Default Notebook Image - PaddleOCR-VL with vLLM
    DEFAULT_IMAGE: str = os.getenv(
        "DEFAULT_IMAGE", 
        "docker.io/vivienfanghua/vllm_paddle:ppocr-oneclick"
    )
    
    # Available Images
    AVAILABLE_IMAGES: list = [
        "docker.io/vivienfanghua/vllm_paddle:ppocr-oneclick",
    ]
    
    # Notebook Configuration
    NOTEBOOK_TOKEN: str = os.getenv("NOTEBOOK_TOKEN", "amd-oneclick")
    NOTEBOOK_PORT: int = 8888
    NOTEBOOK_LABEL_PREFIX: str = "amd-ppocr-vl"
    
    # Resource Limits - Increased for PaddleOCR-VL
    CPU_LIMIT: str = os.getenv("CPU_LIMIT", "128")
    MEMORY_LIMIT: str = os.getenv("MEMORY_LIMIT", "256Gi")
    GPU_LIMIT: str = os.getenv("GPU_LIMIT", "1")
    CPU_REQUEST: str = os.getenv("CPU_REQUEST", "64")
    MEMORY_REQUEST: str = os.getenv("MEMORY_REQUEST", "128Gi")
    
    # Cleanup Configuration
    IDLE_TIMEOUT_MINUTES: int = int(os.getenv("IDLE_TIMEOUT_MINUTES", "10"))
    MAX_LIFETIME_HOURS: int = int(os.getenv("MAX_LIFETIME_HOURS", "6"))
    
    # Email Configuration (optional)
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@amd-oneclick.local")
    
    # Service Configuration
    SERVICE_HOST: str = os.getenv("SERVICE_HOST", "129.212.179.141")
    NODE_PORT_BASE: int = int(os.getenv("NODE_PORT_BASE", "30100"))
    
    # Admin Configuration
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")


settings = Settings()

