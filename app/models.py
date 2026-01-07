"""
Data models for AMD OneClick Notebook Manager
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class NotebookRequest(BaseModel):
    """Request model for creating a notebook instance"""
    email: EmailStr
    image: Optional[str] = None


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


class NotebookStatus(BaseModel):
    """Status response for notebook creation"""
    status: str  # allocating, loading, initializing, ready, failed
    message: str
    url: Optional[str] = None
    email: Optional[str] = None


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


class AdminListResponse(BaseModel):
    """Response for admin list endpoint"""
    instances: list[NotebookListItem]
    total_count: int


class DestroyResponse(BaseModel):
    """Response for destroy operations"""
    success: bool
    message: str
    destroyed_count: int = 0
