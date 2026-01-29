"""
Data models for AMD OneClick Notebook Manager
Extended to support Spaces and Generic Notebooks
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# Resource Configuration Models
# =============================================================================

class ResourceSpec(BaseModel):
    """Resource specification for instances"""
    gpu_type: str = Field(default="cpu", description="GPU type: mi300x, mi355x, r7900, cpu")
    gpu_count: int = Field(default=0, description="Number of GPUs")
    cpu_cores: str = Field(default="4", description="CPU cores limit")
    memory: str = Field(default="16Gi", description="Memory limit")
    storage: str = Field(default="50Gi", description="Storage size")


class ResourcePreset(BaseModel):
    """Predefined resource configuration"""
    id: str
    name: str
    description: str = ""
    spec: ResourceSpec
    available: bool = True


# =============================================================================
# Source Metadata Models
# =============================================================================

class SrcMeta(BaseModel):
    """Source metadata for tracking instance origin"""
    src: str = Field(..., description="Source platform: modelscope, aistudio, github, direct")
    outer_email: Optional[str] = Field(default=None, description="External user email")
    inner_uid: Optional[str] = Field(default=None, description="Internal user ID")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


# =============================================================================
# Space Models
# =============================================================================

class SpaceRequest(BaseModel):
    """Request model for creating a Space instance"""
    repo_url: str = Field(..., description="Git repository URL")
    start_command: str = Field(..., description="Command to start the space")
    src_meta: SrcMeta
    resource_preset: str = Field(default="mi300x-1", description="Resource preset ID")
    # Optional configurations
    docker_image: Optional[str] = Field(default=None, description="Custom Docker image")
    conda_env: Optional[str] = Field(default=None, description="Conda environment: python3.10, python3.11, python3.12")
    custom_port: Optional[int] = Field(default=None, description="Custom exposed port")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables")
    branch: str = Field(default="main", description="Git branch to clone")


class SpaceInstance(BaseModel):
    """Model representing a Space instance"""
    id: str
    repo_url: str
    start_command: str
    src_meta: SrcMeta
    resource_spec: ResourceSpec
    status: str  # pending, cloning, running, failed, terminated
    url: Optional[str] = None
    created_at: datetime
    docker_image: str
    conda_env: Optional[str] = None
    custom_port: Optional[int] = None
    env_vars: Optional[Dict[str, str]] = None
    branch: str = "main"


class SpaceStatus(BaseModel):
    """Status response for Space operations"""
    status: str
    message: str
    url: Optional[str] = None
    space_id: Optional[str] = None
    logs: Optional[str] = None


class SpaceListItem(BaseModel):
    """Item in the space list for admin view"""
    id: str
    repo_url: str
    start_command: str
    src: str  # Source platform
    src_email: Optional[str] = None
    status: str
    url: Optional[str] = None
    created_at: str
    uptime_minutes: int
    gpu_type: str
    gpu_count: int


class SpaceForkRequest(BaseModel):
    """Request to fork an existing Space"""
    src_meta: SrcMeta
    resource_preset: Optional[str] = None  # Use original if not specified


# =============================================================================
# Generic Notebook Models
# =============================================================================

class GenericNotebookRequest(BaseModel):
    """Request model for creating a generic Notebook instance"""
    notebook_url: str = Field(..., description="Notebook URL (GitHub/GitLab raw URL or repo URL)")
    src_meta: SrcMeta
    resource_preset: str = Field(default="mi300x-1", description="Resource preset ID")
    # Optional configurations
    docker_image: Optional[str] = Field(default=None, description="Custom Docker image")
    conda_env: Optional[str] = Field(default=None, description="Conda environment")


class NotebookForkRequest(BaseModel):
    """Request to fork an existing Notebook"""
    src_meta: SrcMeta
    resource_preset: Optional[str] = None


# =============================================================================
# Legacy Notebook Models (maintained for backwards compatibility)
# =============================================================================

class NotebookRequest(BaseModel):
    """Request model for creating a notebook instance (legacy)"""
    email: EmailStr
    image: Optional[str] = None


class GitHubNotebookInfo(BaseModel):
    """GitHub notebook information"""
    org: str
    repo: str
    branch: str
    path: str
    raw_url: str


class NotebookInstance(BaseModel):
    """Model representing a notebook instance"""
    id: str
    email: str
    pod_name: str
    service_name: str
    image: str
    url: str
    status: str  # pending, creating, running, terminating, failed
    created_at: datetime
    last_activity: Optional[datetime] = None
    node_port: Optional[int] = None
    github_info: Optional[GitHubNotebookInfo] = None


class NotebookStatus(BaseModel):
    """Status response for notebook creation"""
    status: str  # allocating, loading, initializing, ready, failed
    message: str
    url: Optional[str] = None
    email: Optional[str] = None
    instance_id: Optional[str] = None


class NotebookListItem(BaseModel):
    """Item in the notebook list for admin view"""
    id: str
    email: str
    pod_name: str
    url: str
    status: str
    created_at: str
    last_activity: Optional[str] = None
    uptime_minutes: int
    github_org: Optional[str] = None
    github_repo: Optional[str] = None
    github_path: Optional[str] = None
    # Extended fields for generic notebooks
    instance_type: str = "notebook"  # notebook, space
    src: Optional[str] = None  # modelscope, aistudio, github, direct
    gpu_type: Optional[str] = None
    gpu_count: Optional[int] = None


class AdminListResponse(BaseModel):
    """Response for admin list endpoint"""
    instances: list[NotebookListItem]
    total_count: int
    # Extended counts
    notebook_count: int = 0
    space_count: int = 0


class AdminSpaceListResponse(BaseModel):
    """Response for admin space list endpoint"""
    spaces: list[SpaceListItem]
    total_count: int


class CombinedAdminResponse(BaseModel):
    """Combined response for all instances"""
    notebooks: list[NotebookListItem]
    spaces: list[SpaceListItem]
    total_notebooks: int
    total_spaces: int


class DestroyResponse(BaseModel):
    """Response for destroy operations"""
    success: bool
    message: str
    destroyed_count: int = 0
