"""
FastAPI main application for AMD OneClick Manager
Extended to support Spaces and Generic Notebooks
"""
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import secrets

try:
    from .config_ppocr import settings
except ImportError:
    try:
        from .config import settings
    except ImportError:
        from config import settings

from .models import (
    NotebookRequest, 
    NotebookStatus, 
    AdminListResponse, 
    NotebookListItem,
    DestroyResponse,
    # New models for Spaces and Generic Notebooks
    SpaceRequest,
    SpaceStatus,
    SpaceListItem,
    SpaceForkRequest,
    GenericNotebookRequest,
    NotebookForkRequest,
    SrcMeta,
    ResourcePreset,
    AdminSpaceListResponse,
    CombinedAdminResponse,
)
from .k8s_client import k8s_client
from .email_service import send_notebook_url_email
from .scheduler import start_scheduler, stop_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting AMD OneClick Notebook Manager")
    start_scheduler()
    yield
    # Shutdown
    logger.info("Shutting down AMD OneClick Notebook Manager")
    stop_scheduler()


app = FastAPI(
    title="AMD OneClick Notebook Manager",
    description="Kubernetes-based Jupyter Notebook instance management",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# HTTP Basic Auth for admin
security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify admin credentials"""
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf8"),
        settings.ADMIN_PASSWORD.encode("utf8")
    )
    if not (credentials.username == "admin" and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# =============================================================================
# User Endpoints
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main request page"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "images": settings.AVAILABLE_IMAGES,
            "default_image": settings.DEFAULT_IMAGE
        }
    )


@app.post("/api/notebook/request", response_model=NotebookStatus)
async def request_notebook(req: NotebookRequest):
    """Request a notebook instance"""
    email = req.email.lower()
    image = req.image or settings.DEFAULT_IMAGE
    
    # Validate image
    if image not in settings.AVAILABLE_IMAGES:
        raise HTTPException(status_code=400, detail="Invalid image selected")
    
    try:
        # Check for existing instance
        existing = k8s_client.get_instance_by_email(email)
        
        if existing:
            status = k8s_client.get_pod_status(email)
            
            if status == "ready" or status == "running":
                return NotebookStatus(
                    status="ready",
                    message="Your notebook is ready!",
                    url=existing["url"],
                    email=email
                )
            elif status in ["pending", "initializing", "loading"]:
                return NotebookStatus(
                    status=status,
                    message="Your notebook is being prepared...",
                    url=existing["url"],
                    email=email
                )
            elif status == "failed":
                # Delete failed instance and recreate
                k8s_client.delete_instance(email)
            else:
                return NotebookStatus(
                    status=status or "unknown",
                    message="Checking notebook status...",
                    url=existing.get("url"),
                    email=email
                )
        
        # Create new instance
        instance = k8s_client.create_instance(email, image)
        
        # Send email notification (async, don't wait)
        if instance.get("url"):
            send_notebook_url_email(email, instance["url"])
        
        return NotebookStatus(
            status="allocating",
            message="Allocating resources for your notebook...",
            url=instance.get("url"),
            email=email
        )
        
    except Exception as e:
        logger.error(f"Error creating notebook for {email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/notebook/status", response_model=NotebookStatus)
async def check_status(email: str = Query(..., description="User email")):
    """Check the status of a notebook instance"""
    email = email.lower()
    
    try:
        instance = k8s_client.get_instance_by_email(email)
        
        if not instance:
            return NotebookStatus(
                status="not_found",
                message="No notebook instance found for this email",
                email=email
            )
        
        status = k8s_client.get_pod_status(email)
        
        status_messages = {
            "ready": "Your notebook is ready!",
            "running": "Container is running, starting Jupyter...",
            "jupyter_starting": "Jupyter is starting up...",
            "pending": "Waiting for resources...",
            "initializing": "Initializing notebook environment...",
            "loading": "Loading notebook image...",
            "failed": "Notebook creation failed",
            "unknown": "Checking status..."
        }
        
        return NotebookStatus(
            status=status or "unknown",
            message=status_messages.get(status, "Checking status..."),
            url=instance.get("url"),
            email=email
        )
        
    except Exception as e:
        logger.error(f"Error checking status for {email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# GitHub Notebook Endpoints
# =============================================================================

def _generate_github_instance_id(org: str, repo: str, path: str, unique: bool = False) -> str:
    """Generate a unique instance ID from GitHub path
    
    Args:
        org: GitHub organization
        repo: GitHub repository  
        path: Path to notebook
        unique: If True, generate a unique ID for each user; if False, shared ID
    """
    if unique:
        # Generate unique ID per user using random component
        import uuid
        random_part = uuid.uuid4().hex[:8]
        return f"gh-{random_part}"
    else:
        # Legacy: shared ID based on GitHub path
        key = f"{org}/{repo}/{path}".lower()
        hash_str = hashlib.md5(key.encode()).hexdigest()[:8]
        return f"gh-{hash_str}"


def _parse_github_path(full_path: str) -> dict:
    """Parse GitHub path like org/repo/blob/branch/path/to/notebook.ipynb"""
    parts = full_path.split("/")
    if len(parts) < 5:
        raise ValueError("Invalid GitHub path format")
    
    org = parts[0]
    repo = parts[1]
    # parts[2] should be 'blob'
    branch = parts[3]
    path = "/".join(parts[4:])
    
    # Construct raw GitHub URL
    raw_url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{path}"
    
    return {
        "org": org,
        "repo": repo,
        "branch": branch,
        "path": path,
        "raw_url": raw_url
    }


@app.get("/github/{full_path:path}", response_class=HTMLResponse)
async def github_notebook(
    request: Request,
    full_path: str,
    response: Response,
    instance_id: Optional[str] = Cookie(None, alias="amd_oneclick_gh_instance")
):
    """Handle GitHub notebook request
    
    Each user gets their own instance (tracked via cookie).
    """
    try:
        github_info = _parse_github_path(full_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if user already has an instance (from cookie)
    if instance_id:
        existing = k8s_client.get_instance_by_id(instance_id)
        if existing:
            status = k8s_client.get_pod_status("", instance_id=instance_id)
            if status == "ready":
                # Redirect directly to notebook
                logger.info(f"Redirecting user to existing instance {instance_id}")
                return RedirectResponse(url=existing["url"], status_code=302)
    
    # Render landing page for status tracking
    # Pass instance_id from cookie (if any) so frontend can check/reuse
    return templates.TemplateResponse(
        "github_landing.html",
        {
            "request": request,
            "github_org": github_info["org"],
            "github_repo": github_info["repo"],
            "github_path": github_info["path"],
            "github_branch": github_info["branch"],
            "instance_id": instance_id or "",  # Pass existing cookie ID if any
            "full_path": full_path
        }
    )


class GitHubNotebookRequest(BaseModel):
    org: str
    repo: str
    branch: str
    path: str


@app.post("/api/github/notebook/create")
async def create_github_notebook(
    request: Request,
    response: Response,
    body: GitHubNotebookRequest,
    existing_instance_id: Optional[str] = Cookie(None, alias="amd_oneclick_gh_instance")
):
    """Create a notebook instance for a GitHub notebook
    
    Each user gets their own instance (tracked via cookie).
    """
    github_info = {
        "org": body.org,
        "repo": body.repo,
        "branch": body.branch,
        "path": body.path,
        "raw_url": f"https://raw.githubusercontent.com/{body.org}/{body.repo}/{body.branch}/{body.path}"
    }
    org = body.org
    repo = body.repo
    path = body.path
    
    # Check if user already has an instance (from cookie)
    if existing_instance_id:
        existing = k8s_client.get_instance_by_id(existing_instance_id)
        if existing:
            logger.info(f"Reusing existing instance {existing_instance_id} for user")
            return NotebookStatus(
                status="exists",
                message="Instance already exists",
                url=existing.get("url"),
                instance_id=existing_instance_id
            )
    
    # Create a new unique instance for this user
    instance_id = _generate_github_instance_id(org, repo, path, unique=True)
    
    try:
        # Use a placeholder email for GitHub notebooks
        email = f"github-{instance_id}@oneclick.local"
        
        instance = k8s_client.create_instance(
            email=email,
            image=settings.DEFAULT_IMAGE,
            github_info=github_info,
            custom_instance_id=instance_id
        )
        
        # Set cookie to remember this instance for this user
        response.set_cookie(
            key="amd_oneclick_gh_instance",
            value=instance_id,
            max_age=86400 * 7,  # 7 days
            httponly=True
        )
        
        logger.info(f"Created new instance {instance_id} for user")
        
        return NotebookStatus(
            status="allocating",
            message="Allocating resources for your notebook...",
            url=instance.get("url"),
            instance_id=instance_id
        )
        
    except Exception as e:
        logger.error(f"Error creating GitHub notebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/github/notebook/status")
async def check_github_status(instance_id: str = Query(...)):
    """Check the status of a GitHub notebook instance"""
    try:
        instance = k8s_client.get_instance_by_id(instance_id)
        
        if not instance:
            return NotebookStatus(
                status="not_found",
                message="No notebook instance found",
                instance_id=instance_id
            )
        
        status = k8s_client.get_pod_status("", instance_id=instance_id)
        
        status_messages = {
            "ready": "Your notebook is ready!",
            "running": "Container is running, starting Jupyter...",
            "jupyter_starting": "Jupyter is starting up...",
            "pending": "Waiting for resources...",
            "initializing": "Initializing notebook environment...",
            "loading": "Loading notebook image...",
            "failed": "Notebook creation failed",
            "unknown": "Checking status..."
        }
        
        return NotebookStatus(
            status=status or "unknown",
            message=status_messages.get(status, "Checking status..."),
            url=instance.get("url"),
            instance_id=instance_id
        )
        
    except Exception as e:
        logger.error(f"Error checking GitHub status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Space API Endpoints
# =============================================================================

@app.post("/api/space/create", response_model=SpaceStatus)
async def create_space(request: SpaceRequest):
    """Create a new Space instance
    
    This endpoint is designed to be called by external services (ModelScope, AIStudio, etc.)
    """
    try:
        logger.info(f"Creating Space from {request.src_meta.src}: {request.repo_url}")
        
        space = k8s_client.create_space(request)
        
        return SpaceStatus(
            status="allocating",
            message="Allocating resources for your Space...",
            url=space.get("url"),
            space_id=space["id"]
        )
        
    except Exception as e:
        logger.error(f"Error creating Space: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/space/{space_id}", response_model=SpaceStatus)
async def get_space_status(space_id: str):
    """Get Space instance status"""
    try:
        space = k8s_client.get_space(space_id)
        
        if not space:
            return SpaceStatus(
                status="not_found",
                message="Space not found",
                space_id=space_id
            )
        
        status = k8s_client.get_space_status(space_id)
        
        status_messages = {
            "ready": "Your Space is ready!",
            "running": "Container is running, starting application...",
            "pending": "Waiting for resources...",
            "initializing": "Initializing Space environment...",
            "loading": "Loading Space image...",
            "failed": "Space creation failed",
            "unknown": "Checking status..."
        }
        
        return SpaceStatus(
            status=status or "unknown",
            message=status_messages.get(status, "Checking status..."),
            url=space.get("url"),
            space_id=space_id
        )
        
    except Exception as e:
        logger.error(f"Error getting Space status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/space/{space_id}/logs")
async def get_space_logs(space_id: str, tail_lines: int = Query(default=100, le=1000)):
    """Get Space instance logs"""
    try:
        logs = k8s_client.get_space_logs(space_id, tail_lines)
        
        if logs is None:
            raise HTTPException(status_code=404, detail="Space not found")
        
        return {
            "space_id": space_id,
            "logs": logs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Space logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/space/{space_id}", response_model=DestroyResponse)
async def delete_space(space_id: str):
    """Delete a Space instance"""
    try:
        success = k8s_client.delete_space(space_id)
        
        return DestroyResponse(
            success=success,
            message=f"Space {space_id} {'deleted' if success else 'not found'}",
            destroyed_count=1 if success else 0
        )
        
    except Exception as e:
        logger.error(f"Error deleting Space: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/space/{space_id}/fork", response_model=SpaceStatus)
async def fork_space(space_id: str, request: SpaceForkRequest):
    """Fork an existing Space to create a new instance"""
    try:
        new_space = k8s_client.fork_space(
            space_id,
            request.src_meta,
            request.resource_preset
        )
        
        if not new_space:
            raise HTTPException(status_code=404, detail="Original Space not found")
        
        return SpaceStatus(
            status="allocating",
            message="Forking Space...",
            url=new_space.get("url"),
            space_id=new_space["id"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forking Space: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Generic Notebook API Endpoints
# =============================================================================

@app.post("/api/notebook/create", response_model=NotebookStatus)
async def create_generic_notebook(request: GenericNotebookRequest):
    """Create a new generic Notebook instance
    
    This endpoint is designed to be called by external services (ModelScope, AIStudio, etc.)
    """
    try:
        logger.info(f"Creating Notebook from {request.src_meta.src}: {request.notebook_url}")
        
        notebook = k8s_client.create_generic_notebook(request)
        
        return NotebookStatus(
            status="allocating",
            message="Allocating resources for your Notebook...",
            url=notebook.get("url"),
            instance_id=notebook["id"]
        )
        
    except Exception as e:
        logger.error(f"Error creating generic Notebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notebook/{instance_id}/fork", response_model=NotebookStatus)
async def fork_notebook(instance_id: str, request: NotebookForkRequest):
    """Fork an existing Notebook to create a new instance"""
    try:
        new_notebook = k8s_client.fork_notebook(
            instance_id,
            request.src_meta,
            request.resource_preset
        )
        
        if not new_notebook:
            raise HTTPException(status_code=404, detail="Original Notebook not found or cannot be forked")
        
        return NotebookStatus(
            status="allocating",
            message="Forking Notebook...",
            url=new_notebook.get("url"),
            instance_id=new_notebook["id"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forking Notebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Configuration API Endpoints
# =============================================================================

@app.get("/api/config/resources")
async def get_resource_presets():
    """Get available resource configurations"""
    try:
        if hasattr(settings, 'get_available_presets'):
            presets = settings.get_available_presets()
            return {
                "presets": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "spec": p.spec.model_dump(),
                        "available": p.available
                    }
                    for p in presets
                ]
            }
        else:
            # Fallback for legacy config
            return {
                "presets": [
                    {
                        "id": "mi300x-1",
                        "name": "AMD MI300X x1",
                        "description": "Single MI300X GPU",
                        "spec": {
                            "gpu_type": "mi300x",
                            "gpu_count": 1,
                            "cpu_cores": "64",
                            "memory": "128Gi"
                        },
                        "available": True
                    }
                ]
            }
    except Exception as e:
        logger.error(f"Error getting resource presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/images")
async def get_available_images():
    """Get available Docker images"""
    try:
        if hasattr(settings, 'AVAILABLE_IMAGES') and isinstance(settings.AVAILABLE_IMAGES, dict):
            return {
                "images": [
                    {"key": key, "url": url}
                    for key, url in settings.AVAILABLE_IMAGES.items()
                ]
            }
        else:
            # Fallback for legacy config (list format)
            images = getattr(settings, 'AVAILABLE_IMAGES', [])
            return {
                "images": [
                    {"key": img.split("/")[-1].split(":")[0], "url": img}
                    for img in images
                ]
            }
    except Exception as e:
        logger.error(f"Error getting available images: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/envs")
async def get_conda_environments():
    """Get available Conda environments"""
    try:
        if hasattr(settings, 'CONDA_ENVS'):
            return {
                "environments": [
                    {"name": name, "url": url}
                    for name, url in settings.CONDA_ENVS.items()
                ]
            }
        else:
            return {"environments": []}
    except Exception as e:
        logger.error(f"Error getting conda environments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Admin Endpoints
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, username: str = Depends(verify_admin)):
    """Render the admin management page"""
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username
        }
    )


@app.get("/api/admin/instances", response_model=AdminListResponse)
async def list_instances(
    username: str = Depends(verify_admin),
    src: Optional[str] = Query(None, description="Filter by source (modelscope, aistudio, github)"),
    gpu_type: Optional[str] = Query(None, description="Filter by GPU type (mi300x, mi355x, r7900, cpu)")
):
    """List all notebook instances with optional filtering"""
    try:
        instances = k8s_client.list_instances()
        
        # Apply filters
        if src:
            instances = [i for i in instances if i.get("src") == src]
        if gpu_type:
            instances = [i for i in instances if i.get("gpu_type") == gpu_type]
        
        items = [
            NotebookListItem(
                id=inst["id"],
                email=inst["email"],
                pod_name=inst["pod_name"],
                url=inst.get("url", ""),
                status=inst["status"],
                created_at=inst.get("created_at", ""),
                last_activity=inst.get("last_activity"),
                uptime_minutes=inst.get("uptime_minutes", 0),
                github_org=inst.get("github_org"),
                github_repo=inst.get("github_repo"),
                github_path=inst.get("github_path"),
                instance_type="notebook",
                src=inst.get("src"),
                gpu_type=inst.get("gpu_type"),
                gpu_count=inst.get("gpu_count")
            )
            for inst in instances
        ]
        
        return AdminListResponse(
            instances=items,
            total_count=len(items),
            notebook_count=len(items),
            space_count=0
        )
        
    except Exception as e:
        logger.error(f"Error listing instances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/instance/{instance_id}", response_model=DestroyResponse)
async def destroy_instance(instance_id: str, username: str = Depends(verify_admin)):
    """Destroy a specific notebook instance by ID"""
    try:
        success = k8s_client.delete_instance_by_id(instance_id)
        
        return DestroyResponse(
            success=success,
            message=f"Instance {instance_id} {'destroyed' if success else 'not found'}",
            destroyed_count=1 if success else 0
        )
        
    except Exception as e:
        logger.error(f"Error destroying instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/instances/all", response_model=DestroyResponse)
async def destroy_all_instances(username: str = Depends(verify_admin)):
    """Destroy all notebook instances"""
    try:
        count = k8s_client.delete_all_instances()
        
        return DestroyResponse(
            success=True,
            message=f"Destroyed {count} instances",
            destroyed_count=count
        )
        
    except Exception as e:
        logger.error(f"Error destroying all instances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/cleanup")
async def trigger_cleanup(username: str = Depends(verify_admin)):
    """Manually trigger cleanup of idle instances"""
    try:
        cleaned = k8s_client.cleanup_idle_instances()
        
        return {
            "success": True,
            "message": f"Cleaned up {len(cleaned)} instances",
            "cleaned": cleaned
        }
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Admin Space Endpoints
# =============================================================================

@app.get("/api/admin/spaces", response_model=AdminSpaceListResponse)
async def list_spaces(
    username: str = Depends(verify_admin),
    src: Optional[str] = Query(None, description="Filter by source (modelscope, aistudio, github)"),
    gpu_type: Optional[str] = Query(None, description="Filter by GPU type")
):
    """List all Space instances with optional filtering"""
    try:
        spaces = k8s_client.list_spaces()
        
        # Apply filters
        if src:
            spaces = [s for s in spaces if s.get("src") == src]
        if gpu_type:
            spaces = [s for s in spaces if s.get("gpu_type") == gpu_type]
        
        items = [
            SpaceListItem(
                id=sp["id"],
                repo_url=sp["repo_url"],
                start_command=sp["start_command"],
                src=sp.get("src", ""),
                src_email=sp.get("src_email"),
                status=sp["status"],
                url=sp.get("url"),
                created_at=sp.get("created_at", ""),
                uptime_minutes=sp.get("uptime_minutes", 0),
                gpu_type=sp.get("gpu_type", "unknown"),
                gpu_count=sp.get("gpu_count", 1)
            )
            for sp in spaces
        ]
        
        return AdminSpaceListResponse(
            spaces=items,
            total_count=len(items)
        )
        
    except Exception as e:
        logger.error(f"Error listing spaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/space/{space_id}", response_model=DestroyResponse)
async def admin_destroy_space(space_id: str, username: str = Depends(verify_admin)):
    """Destroy a specific Space instance by ID (admin)"""
    try:
        success = k8s_client.delete_space(space_id)
        
        return DestroyResponse(
            success=success,
            message=f"Space {space_id} {'destroyed' if success else 'not found'}",
            destroyed_count=1 if success else 0
        )
        
    except Exception as e:
        logger.error(f"Error destroying Space {space_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/spaces/all", response_model=DestroyResponse)
async def destroy_all_spaces(username: str = Depends(verify_admin)):
    """Destroy all Space instances"""
    try:
        count = k8s_client.delete_all_spaces()
        
        return DestroyResponse(
            success=True,
            message=f"Destroyed {count} spaces",
            destroyed_count=count
        )
        
    except Exception as e:
        logger.error(f"Error destroying all spaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/cleanup/all")
async def trigger_cleanup_all(username: str = Depends(verify_admin)):
    """Manually trigger cleanup of both idle notebooks and spaces"""
    try:
        result = k8s_client.cleanup_all_idle()
        
        total_cleaned = len(result.get("notebooks", [])) + len(result.get("spaces", []))
        
        return {
            "success": True,
            "message": f"Cleaned up {total_cleaned} instances",
            "notebooks_cleaned": result.get("notebooks", []),
            "spaces_cleaned": result.get("spaces", [])
        }
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/all", response_model=CombinedAdminResponse)
async def list_all_instances(
    username: str = Depends(verify_admin),
    src: Optional[str] = Query(None, description="Filter by source"),
    gpu_type: Optional[str] = Query(None, description="Filter by GPU type")
):
    """List all instances (notebooks and spaces) combined"""
    try:
        # Get notebooks
        notebooks = k8s_client.list_instances()
        if src:
            notebooks = [n for n in notebooks if n.get("src") == src]
        if gpu_type:
            notebooks = [n for n in notebooks if n.get("gpu_type") == gpu_type]
        
        notebook_items = [
            NotebookListItem(
                id=inst["id"],
                email=inst["email"],
                pod_name=inst["pod_name"],
                url=inst.get("url", ""),
                status=inst["status"],
                created_at=inst.get("created_at", ""),
                last_activity=inst.get("last_activity"),
                uptime_minutes=inst.get("uptime_minutes", 0),
                github_org=inst.get("github_org"),
                github_repo=inst.get("github_repo"),
                github_path=inst.get("github_path"),
                instance_type="notebook",
                src=inst.get("src"),
                gpu_type=inst.get("gpu_type"),
                gpu_count=inst.get("gpu_count")
            )
            for inst in notebooks
        ]
        
        # Get spaces
        spaces = k8s_client.list_spaces()
        if src:
            spaces = [s for s in spaces if s.get("src") == src]
        if gpu_type:
            spaces = [s for s in spaces if s.get("gpu_type") == gpu_type]
        
        space_items = [
            SpaceListItem(
                id=sp["id"],
                repo_url=sp["repo_url"],
                start_command=sp["start_command"],
                src=sp.get("src", ""),
                src_email=sp.get("src_email"),
                status=sp["status"],
                url=sp.get("url"),
                created_at=sp.get("created_at", ""),
                uptime_minutes=sp.get("uptime_minutes", 0),
                gpu_type=sp.get("gpu_type", "unknown"),
                gpu_count=sp.get("gpu_count", 1)
            )
            for sp in spaces
        ]
        
        return CombinedAdminResponse(
            notebooks=notebook_items,
            spaces=space_items,
            total_notebooks=len(notebook_items),
            total_spaces=len(space_items)
        )
        
    except Exception as e:
        logger.error(f"Error listing all instances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/config")
async def get_config():
    """Get public configuration"""
    config = {
        "available_images": settings.AVAILABLE_IMAGES,
        "default_image": getattr(settings, 'DEFAULT_IMAGE', ''),
        "default_notebook_image": getattr(settings, 'DEFAULT_NOTEBOOK_IMAGE', getattr(settings, 'DEFAULT_IMAGE', '')),
        "default_space_image": getattr(settings, 'DEFAULT_SPACE_IMAGE', getattr(settings, 'DEFAULT_IMAGE', '')),
        "max_lifetime_hours": settings.MAX_LIFETIME_HOURS,
        "idle_timeout_minutes": settings.IDLE_TIMEOUT_MINUTES,
        "notebook_port": settings.NOTEBOOK_PORT,
        "space_default_port": getattr(settings, 'SPACE_DEFAULT_PORT', 7860),
    }
    
    # Include resource presets if available
    if hasattr(settings, 'get_available_presets'):
        presets = settings.get_available_presets()
        config["resource_presets"] = [p.id for p in presets]
    
    # Include conda environments if available
    if hasattr(settings, 'CONDA_ENVS'):
        config["conda_environments"] = list(settings.CONDA_ENVS.keys())
    
    return config
