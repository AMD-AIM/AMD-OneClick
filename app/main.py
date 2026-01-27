"""
FastAPI main application for AMD OneClick Notebook Manager
"""
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Request, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import secrets

try:
    from .config_ppocr import settings
except ImportError:
    from .config import settings
from .models import (
    NotebookRequest, 
    NotebookStatus, 
    AdminListResponse, 
    NotebookListItem,
    DestroyResponse
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
async def list_instances(username: str = Depends(verify_admin)):
    """List all notebook instances"""
    try:
        instances = k8s_client.list_instances()
        
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
                github_path=inst.get("github_path")
            )
            for inst in instances
        ]
        
        return AdminListResponse(
            instances=items,
            total_count=len(items)
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
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/config")
async def get_config():
    """Get public configuration"""
    return {
        "available_images": settings.AVAILABLE_IMAGES,
        "default_image": settings.DEFAULT_IMAGE,
        "max_lifetime_hours": settings.MAX_LIFETIME_HOURS,
        "idle_timeout_minutes": settings.IDLE_TIMEOUT_MINUTES
    }
