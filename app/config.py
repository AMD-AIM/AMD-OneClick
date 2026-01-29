"""
Configuration settings for AMD OneClick Manager
Extended to support Spaces, Generic Notebooks, and Resource Presets
"""
import os
from typing import Optional, Dict, List
from .models import ResourceSpec, ResourcePreset


class Settings:
    """Main configuration settings"""
    
    # ==========================================================================
    # K8s Configuration
    # ==========================================================================
    K8S_NAMESPACE: str = os.getenv("K8S_NAMESPACE", "default")
    
    # ==========================================================================
    # Instance Labels
    # ==========================================================================
    APP_LABEL: str = "amd-oneclick"
    NOTEBOOK_LABEL_PREFIX: str = os.getenv("NOTEBOOK_LABEL_PREFIX", "amd-oneclick-notebook")
    SPACE_LABEL_PREFIX: str = os.getenv("SPACE_LABEL_PREFIX", "amd-oneclick-space")
    
    # ==========================================================================
    # Default Images
    # ==========================================================================
    DEFAULT_NOTEBOOK_IMAGE: str = os.getenv(
        "DEFAULT_NOTEBOOK_IMAGE",
        "rocm/vllm-dev:nightly_main_20260125"
    )
    
    DEFAULT_SPACE_IMAGE: str = os.getenv(
        "DEFAULT_SPACE_IMAGE",
        "rocm/vllm-dev:nightly_main_20260125"
    )
    
    # Legacy compatibility
    DEFAULT_IMAGE: str = os.getenv(
        "DEFAULT_IMAGE",
        "docker.io/vivienfanghua/vllm_paddle:ppocr-oneclick"
    )
    
    # ==========================================================================
    # Available Docker Images
    # ==========================================================================
    AVAILABLE_IMAGES: Dict[str, str] = {
        "default": "rocm/vllm-dev:nightly_main_20260125",
        "pytorch": "rocm/pytorch:rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.7.1",
        "paddleocr": "docker.io/vivienfanghua/vllm_paddle:ppocr-oneclick",
        "vllm": "rocm/vllm-dev:nightly_main_20260125",
    }
    
    # ==========================================================================
    # Resource Presets
    # ==========================================================================
    RESOURCE_PRESETS: Dict[str, ResourcePreset] = {
        "cpu-free": ResourcePreset(
            id="cpu-free",
            name="Free CPU",
            description="CPU-only instance, free tier",
            spec=ResourceSpec(
                gpu_type="cpu",
                gpu_count=0,
                cpu_cores="4",
                memory="8Gi",
                storage="20Gi"
            ),
            available=True
        ),
        "mi300x-1": ResourcePreset(
            id="mi300x-1",
            name="AMD MI300X x1",
            description="Single MI300X GPU with 128 CPU cores",
            spec=ResourceSpec(
                gpu_type="mi300x",
                gpu_count=1,
                cpu_cores="64",
                memory="128Gi",
                storage="100Gi"
            ),
            available=True
        ),
        "mi300x-2": ResourcePreset(
            id="mi300x-2",
            name="AMD MI300X x2",
            description="Dual MI300X GPUs with 128 CPU cores",
            spec=ResourceSpec(
                gpu_type="mi300x",
                gpu_count=2,
                cpu_cores="128",
                memory="256Gi",
                storage="200Gi"
            ),
            available=True
        ),
        "mi300x-4": ResourcePreset(
            id="mi300x-4",
            name="AMD MI300X x4",
            description="4x MI300X GPUs with 256 CPU cores",
            spec=ResourceSpec(
                gpu_type="mi300x",
                gpu_count=4,
                cpu_cores="256",
                memory="512Gi",
                storage="500Gi"
            ),
            available=True
        ),
        "mi300x-8": ResourcePreset(
            id="mi300x-8",
            name="AMD MI300X x8",
            description="8x MI300X GPUs with 512 CPU cores",
            spec=ResourceSpec(
                gpu_type="mi300x",
                gpu_count=8,
                cpu_cores="512",
                memory="1024Gi",
                storage="1000Gi"
            ),
            available=True
        ),
        # MI355X presets (not yet available)
        "mi355x-1": ResourcePreset(
            id="mi355x-1",
            name="AMD MI355X x1",
            description="Single MI355X GPU",
            spec=ResourceSpec(
                gpu_type="mi355x",
                gpu_count=1,
                cpu_cores="64",
                memory="128Gi",
                storage="100Gi"
            ),
            available=False  # Not yet available in cluster
        ),
        "mi355x-2": ResourcePreset(
            id="mi355x-2",
            name="AMD MI355X x2",
            description="Dual MI355X GPUs",
            spec=ResourceSpec(
                gpu_type="mi355x",
                gpu_count=2,
                cpu_cores="128",
                memory="256Gi",
                storage="200Gi"
            ),
            available=False
        ),
        "mi355x-4": ResourcePreset(
            id="mi355x-4",
            name="AMD MI355X x4",
            description="4x MI355X GPUs",
            spec=ResourceSpec(
                gpu_type="mi355x",
                gpu_count=4,
                cpu_cores="256",
                memory="512Gi",
                storage="500Gi"
            ),
            available=False
        ),
        "mi355x-8": ResourcePreset(
            id="mi355x-8",
            name="AMD MI355X x8",
            description="8x MI355X GPUs",
            spec=ResourceSpec(
                gpu_type="mi355x",
                gpu_count=8,
                cpu_cores="512",
                memory="1024Gi",
                storage="1000Gi"
            ),
            available=False
        ),
        # R7900 presets (not yet available)
        "r7900-1": ResourcePreset(
            id="r7900-1",
            name="AMD Radeon R7900 x1",
            description="Single R7900 GPU",
            spec=ResourceSpec(
                gpu_type="r7900",
                gpu_count=1,
                cpu_cores="16",
                memory="32Gi",
                storage="50Gi"
            ),
            available=False
        ),
        "r7900-2": ResourcePreset(
            id="r7900-2",
            name="AMD Radeon R7900 x2",
            description="Dual R7900 GPUs",
            spec=ResourceSpec(
                gpu_type="r7900",
                gpu_count=2,
                cpu_cores="32",
                memory="64Gi",
                storage="100Gi"
            ),
            available=False
        ),
        "r7900-4": ResourcePreset(
            id="r7900-4",
            name="AMD Radeon R7900 x4",
            description="4x R7900 GPUs",
            spec=ResourceSpec(
                gpu_type="r7900",
                gpu_count=4,
                cpu_cores="64",
                memory="128Gi",
                storage="200Gi"
            ),
            available=False
        ),
    }
    
    # ==========================================================================
    # Conda Environments (remote tar packages)
    # ==========================================================================
    CONDA_ENVS: Dict[str, str] = {
        "python3.10": os.getenv(
            "CONDA_PYTHON310_URL",
            "https://storage.example.com/conda/conda-python310.tar.gz"
        ),
        "python3.11": os.getenv(
            "CONDA_PYTHON311_URL",
            "https://storage.example.com/conda/conda-python311.tar.gz"
        ),
        "python3.12": os.getenv(
            "CONDA_PYTHON312_URL",
            "https://storage.example.com/conda/conda-python312.tar.gz"
        ),
    }
    
    # ==========================================================================
    # GPU Type to K8s Resource Mapping
    # ==========================================================================
    GPU_RESOURCE_NAMES: Dict[str, str] = {
        "mi300x": "amd.com/gpu",
        "mi355x": "amd.com/gpu",
        "r7900": "amd.com/gpu",
        "cpu": None,  # No GPU resource needed
    }
    
    # GPU Type to Node Selector Mapping
    GPU_NODE_SELECTORS: Dict[str, Dict[str, str]] = {
        "mi300x": {"doks.digitalocean.com/gpu-model": "mi300x"},
        "mi355x": {"doks.digitalocean.com/gpu-model": "mi355x"},
        "r7900": {"doks.digitalocean.com/gpu-model": "r7900"},
        "cpu": {},  # No node selector for CPU
    }
    
    # ==========================================================================
    # Notebook Configuration
    # ==========================================================================
    NOTEBOOK_TOKEN: str = os.getenv("NOTEBOOK_TOKEN", "amd-oneclick")
    NOTEBOOK_PORT: int = int(os.getenv("NOTEBOOK_PORT", "8888"))
    
    # ==========================================================================
    # Space Configuration
    # ==========================================================================
    SPACE_DEFAULT_PORT: int = int(os.getenv("SPACE_DEFAULT_PORT", "7860"))
    
    # ==========================================================================
    # Legacy Resource Limits (for backward compatibility)
    # ==========================================================================
    CPU_LIMIT: str = os.getenv("CPU_LIMIT", "128")
    MEMORY_LIMIT: str = os.getenv("MEMORY_LIMIT", "256Gi")
    GPU_LIMIT: str = os.getenv("GPU_LIMIT", "1")
    CPU_REQUEST: str = os.getenv("CPU_REQUEST", "64")
    MEMORY_REQUEST: str = os.getenv("MEMORY_REQUEST", "128Gi")
    
    # ==========================================================================
    # Cleanup Configuration
    # ==========================================================================
    IDLE_TIMEOUT_MINUTES: int = int(os.getenv("IDLE_TIMEOUT_MINUTES", "10"))
    MAX_LIFETIME_HOURS: int = int(os.getenv("MAX_LIFETIME_HOURS", "6"))
    
    # ==========================================================================
    # Email Configuration (optional)
    # ==========================================================================
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@amd-oneclick.local")
    
    # ==========================================================================
    # Service Configuration
    # ==========================================================================
    SERVICE_HOST: str = os.getenv("SERVICE_HOST", "ocr.oneclickamd.ai")
    NODE_PORT_BASE: int = int(os.getenv("NODE_PORT_BASE", "30100"))
    
    # ==========================================================================
    # Admin Configuration
    # ==========================================================================
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # ==========================================================================
    # Helper Methods
    # ==========================================================================
    @classmethod
    def get_resource_preset(cls, preset_id: str) -> Optional[ResourcePreset]:
        """Get resource preset by ID"""
        return cls.RESOURCE_PRESETS.get(preset_id)
    
    @classmethod
    def get_available_presets(cls) -> List[ResourcePreset]:
        """Get all available resource presets"""
        return [p for p in cls.RESOURCE_PRESETS.values() if p.available]
    
    @classmethod
    def get_image_url(cls, image_key: str) -> Optional[str]:
        """Get Docker image URL by key"""
        return cls.AVAILABLE_IMAGES.get(image_key, image_key)
    
    @classmethod
    def get_conda_env_url(cls, env_name: str) -> Optional[str]:
        """Get Conda environment download URL"""
        return cls.CONDA_ENVS.get(env_name)
    
    @classmethod
    def get_gpu_resource_name(cls, gpu_type: str) -> Optional[str]:
        """Get K8s GPU resource name for a GPU type"""
        return cls.GPU_RESOURCE_NAMES.get(gpu_type)
    
    @classmethod
    def get_node_selector(cls, gpu_type: str) -> Dict[str, str]:
        """Get K8s node selector for a GPU type"""
        return cls.GPU_NODE_SELECTORS.get(gpu_type, {})


# Global settings instance
settings = Settings()
