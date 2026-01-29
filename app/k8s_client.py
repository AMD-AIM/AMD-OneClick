"""
Kubernetes client for managing notebook and space instances
Extended to support Spaces, Generic Notebooks, and Dynamic Resource Configuration
"""
import hashlib
import logging
import socket
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

try:
    from .config import settings
except ImportError:
    try:
        from .config_ppocr import settings
    except ImportError:
        from config import settings

from .models import (
    ResourceSpec, SrcMeta, SpaceRequest, SpaceInstance,
    GenericNotebookRequest
)

logger = logging.getLogger(__name__)


class K8sClient:
    """Kubernetes client for notebook and space management"""
    
    def __init__(self):
        """Initialize K8s client"""
        try:
            # Try in-cluster config first (when running inside K8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster K8s config")
        except config.ConfigException:
            # Fall back to kubeconfig file
            config.load_kube_config()
            logger.info("Loaded kubeconfig file")
        
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.namespace = settings.K8S_NAMESPACE
    
    # =========================================================================
    # ID Generation Methods
    # =========================================================================
    
    def _generate_instance_id(self, email: str) -> str:
        """Generate a unique instance ID from email (legacy notebooks)"""
        hash_str = hashlib.md5(email.lower().encode()).hexdigest()[:8]
        return f"nb-{hash_str}"
    
    def _generate_space_id(self, repo_url: str, src_meta: SrcMeta) -> str:
        """Generate a unique Space ID"""
        key = f"{src_meta.src}:{src_meta.inner_uid or src_meta.outer_email}:{repo_url}"
        hash_str = hashlib.md5(key.encode()).hexdigest()[:8]
        return f"aideploy-space-{hash_str}"
    
    def _generate_unique_id(self, prefix: str = "inst") -> str:
        """Generate a unique random ID"""
        return f"{prefix}-{uuid.uuid4().hex[:8]}"
    
    def _generate_notebook_id(self) -> str:
        """Generate a unique Notebook ID"""
        return f"aideploy-nb-{uuid.uuid4().hex[:8]}"
    
    # =========================================================================
    # Label Generation Methods
    # =========================================================================
    
    def _get_labels(self, email: str, instance_id: str) -> dict:
        """Generate labels for K8s resources (legacy notebooks)"""
        return {
            "app": settings.NOTEBOOK_LABEL_PREFIX,
            "instance-id": instance_id,
            "email-hash": hashlib.md5(email.lower().encode()).hexdigest()[:16],
        }
    
    def _get_space_labels(self, space_id: str, src_meta: SrcMeta, 
                          resource_spec: ResourceSpec) -> dict:
        """Generate labels for Space K8s resources"""
        label_prefix = getattr(settings, 'SPACE_LABEL_PREFIX', 'amd-oneclick-space')
        return {
            "app": label_prefix,
            "instance-type": "space",
            "instance-id": space_id,
            "src": src_meta.src,
            "gpu-type": resource_spec.gpu_type,
        }
    
    def _get_generic_notebook_labels(self, instance_id: str, src_meta: SrcMeta,
                                     resource_spec: ResourceSpec) -> dict:
        """Generate labels for generic Notebook K8s resources"""
        label_prefix = getattr(settings, 'NOTEBOOK_LABEL_PREFIX', 'amd-oneclick-notebook')
        return {
            "app": label_prefix,
            "instance-type": "notebook",
            "instance-id": instance_id,
            "src": src_meta.src,
            "gpu-type": resource_spec.gpu_type,
        }
    
    # =========================================================================
    # Resource Spec Helper Methods
    # =========================================================================
    
    def _get_resource_spec_from_preset(self, preset_id: str) -> ResourceSpec:
        """Get ResourceSpec from preset ID"""
        if hasattr(settings, 'get_resource_preset'):
            preset = settings.get_resource_preset(preset_id)
            if preset:
                return preset.spec
        # Default fallback
        return ResourceSpec(
            gpu_type="mi300x",
            gpu_count=1,
            cpu_cores="64",
            memory="128Gi",
            storage="100Gi"
        )
    
    def _build_resource_requirements(self, resource_spec: ResourceSpec) -> dict:
        """Build K8s resource requirements from ResourceSpec"""
        resources = {
            "limits": {
                "cpu": resource_spec.cpu_cores,
                "memory": resource_spec.memory,
            },
            "requests": {
                "cpu": str(int(int(resource_spec.cpu_cores) / 2)),  # Request half of limit
                "memory": resource_spec.memory,
            }
        }
        
        # Add GPU resources if needed
        if resource_spec.gpu_count > 0:
            gpu_resource_name = "amd.com/gpu"
            if hasattr(settings, 'get_gpu_resource_name'):
                gpu_resource_name = settings.get_gpu_resource_name(resource_spec.gpu_type) or "amd.com/gpu"
            
            resources["limits"][gpu_resource_name] = str(resource_spec.gpu_count)
            resources["requests"][gpu_resource_name] = str(resource_spec.gpu_count)
        
        return resources
    
    def _build_node_selector(self, resource_spec: ResourceSpec) -> dict:
        """Build K8s node selector from ResourceSpec"""
        if hasattr(settings, 'get_node_selector'):
            return settings.get_node_selector(resource_spec.gpu_type)
        
        # Default node selectors
        if resource_spec.gpu_type == "mi300x":
            return {"doks.digitalocean.com/gpu-model": "mi300x"}
        elif resource_spec.gpu_type in ["mi355x", "r7900"]:
            return {"doks.digitalocean.com/gpu-model": resource_spec.gpu_type}
        return {}
    
    def _build_tolerations(self, resource_spec: ResourceSpec) -> list:
        """Build K8s tolerations from ResourceSpec"""
        tolerations = []
        if resource_spec.gpu_count > 0:
            tolerations.append({
                "key": "amd.com/gpu",
                "operator": "Exists",
                "effect": "NoSchedule"
            })
        return tolerations
    
    def _get_pod_manifest(self, email: str, instance_id: str, image: str, 
                          github_info: Optional[dict] = None) -> dict:
        """Generate Pod manifest"""
        labels = self._get_labels(email, instance_id)
        
        annotations = {
            "amd-oneclick/email": email,
            "amd-oneclick/created-at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Add GitHub info to annotations if provided
        if github_info:
            annotations["amd-oneclick/github-org"] = github_info.get("org", "")
            annotations["amd-oneclick/github-repo"] = github_info.get("repo", "")
            annotations["amd-oneclick/github-branch"] = github_info.get("branch", "")
            annotations["amd-oneclick/github-path"] = github_info.get("path", "")
            annotations["amd-oneclick/github-raw-url"] = github_info.get("raw_url", "")
        
        # Build the startup command
        if github_info:
            # Download the notebook file before starting Jupyter
            notebook_filename = github_info["path"].split("/")[-1]
            startup_script = f"""
export NOTEBOOK_URL='{github_info["raw_url"]}'
export NOTEBOOK_TOKEN='{settings.NOTEBOOK_TOKEN}'
export JUPYTER_PORT={settings.NOTEBOOK_PORT}
exec /opt/PaddleX/oneclick_entrypoint.sh
"""
        else:
            startup_script = f"""
export NOTEBOOK_TOKEN='{settings.NOTEBOOK_TOKEN}'
export JUPYTER_PORT={settings.NOTEBOOK_PORT}
exec /opt/PaddleX/oneclick_entrypoint.sh
"""
        
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": instance_id,
                "namespace": self.namespace,
                "labels": labels,
                "annotations": annotations
            },
            "spec": {
                "tolerations": [
                    {
                        "key": "amd.com/gpu",
                        "operator": "Exists",
                        "effect": "NoSchedule"
                    }
                ],
                "containers": [
                    {
                        "name": "notebook",
                        "image": image,
                        "imagePullPolicy": "Always",
                        "command": ["/bin/bash", "-c"],
                        "args": [startup_script],
                        "ports": [
                            {
                                "containerPort": settings.NOTEBOOK_PORT,
                                "name": "jupyter"
                            }
                        ],
                        "resources": {
                            "limits": {
                                "cpu": settings.CPU_LIMIT,
                                "memory": settings.MEMORY_LIMIT,
                                "amd.com/gpu": settings.GPU_LIMIT
                            },
                            "requests": {
                                "cpu": settings.CPU_REQUEST,
                                "memory": settings.MEMORY_REQUEST,
                                "amd.com/gpu": settings.GPU_LIMIT
                            }
                        },
                        "env": [
                            {"name": "SHELL", "value": "/bin/bash"},
                            {"name": "USER_EMAIL", "value": email},
                            {"name": "GPU_MEMORY_UTILIZATION", "value": "0.85"},
                            {"name": "INSTANCE_ID", "value": instance_id}
                        ],
                        "volumeMounts": [
                            {"name": "shm", "mountPath": "/dev/shm"}
                        ]
                    }
                ],
                "volumes": [
                    {
                        "name": "shm",
                        "emptyDir": {
                            "medium": "Memory",
                            "sizeLimit": "64Gi"
                        }
                    }
                ],
                "restartPolicy": "Always"
            }
        }
    
    def _get_service_manifest(self, email: str, instance_id: str) -> dict:
        """Generate Service manifest (ClusterIP for Nginx proxy)"""
        labels = self._get_labels(email, instance_id)
        
        # Service name: notebook-{instance_id} for easy DNS resolution
        # Nginx will proxy to: notebook-{instance_id}.default.svc.cluster.local
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"notebook-{instance_id}",
                "namespace": self.namespace,
                "labels": labels,
            },
            "spec": {
                "selector": labels,
                "type": "ClusterIP",
                "ports": [
                    {
                        "name": "jupyter",
                        "port": settings.NOTEBOOK_PORT,
                        "targetPort": settings.NOTEBOOK_PORT
                    }
                ]
            }
        }
    
    def get_instance_by_email(self, email: str) -> Optional[dict]:
        """Get existing notebook instance for an email"""
        instance_id = self._generate_instance_id(email)
        
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
            
            # Check if service exists
            service_exists = False
            try:
                self.core_v1.read_namespaced_service(
                    name=f"notebook-{instance_id}",
                    namespace=self.namespace
                )
                service_exists = True
            except ApiException:
                pass
            
            return {
                "id": instance_id,
                "email": email,
                "pod_name": pod.metadata.name,
                "service_name": f"notebook-{instance_id}",
                "image": pod.spec.containers[0].image,
                "status": pod.status.phase.lower(),
                "created_at": pod.metadata.creation_timestamp,
                "url": self._build_url(instance_id) if service_exists else None
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def _build_url(self, instance_id: str, notebook_path: Optional[str] = None) -> str:
        """Build notebook URL via Nginx proxy
        
        Returns URL in format: https://{SERVICE_HOST}/instance/{instance_id}/lab?token=xxx
        This URL is proxied by Nginx to the actual notebook service.
        """
        # Use HTTPS for domain names, HTTP for IP addresses
        protocol = "https" if not settings.SERVICE_HOST.replace(".", "").isdigit() else "http"
        base_url = f"{protocol}://{settings.SERVICE_HOST}/instance/{instance_id}/lab?token={settings.NOTEBOOK_TOKEN}"
        if notebook_path:
            # Add notebook path to URL for direct open
            notebook_filename = notebook_path.split("/")[-1]
            return f"{protocol}://{settings.SERVICE_HOST}/instance/{instance_id}/lab/tree/{notebook_filename}?token={settings.NOTEBOOK_TOKEN}"
        return base_url
    
    def create_instance(self, email: str, image: Optional[str] = None, 
                        github_info: Optional[dict] = None,
                        custom_instance_id: Optional[str] = None) -> dict:
        """Create a new notebook instance"""
        instance_id = custom_instance_id or self._generate_instance_id(email)
        image = image or settings.DEFAULT_IMAGE
        
        # Check if instance already exists
        existing = self.get_instance_by_id(instance_id)
        if existing:
            return existing
        
        # Create Pod
        pod_manifest = self._get_pod_manifest(email, instance_id, image, github_info)
        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created pod {instance_id} for {email}")
        except ApiException as e:
            logger.error(f"Failed to create pod: {e}")
            raise
        
        # Create ClusterIP Service (for Nginx proxy)
        svc_manifest = self._get_service_manifest(email, instance_id)
        try:
            self.core_v1.create_namespaced_service(
                namespace=self.namespace,
                body=svc_manifest
            )
            logger.info(f"Created service notebook-{instance_id} (ClusterIP)")
        except ApiException as e:
            logger.error(f"Failed to create service: {e}")
            # Cleanup pod if service creation fails
            self.delete_instance_by_id(instance_id)
            raise
        
        notebook_path = github_info.get("path") if github_info else None
        
        return {
            "id": instance_id,
            "email": email,
            "pod_name": instance_id,
            "service_name": f"notebook-{instance_id}",
            "image": image,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "url": self._build_url(instance_id, notebook_path),
            "github_info": github_info
        }
    
    def get_instance_by_id(self, instance_id: str) -> Optional[dict]:
        """Get existing notebook instance by instance ID"""
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
            
            # Check if service exists
            service_exists = False
            try:
                self.core_v1.read_namespaced_service(
                    name=f"notebook-{instance_id}",
                    namespace=self.namespace
                )
                service_exists = True
            except ApiException:
                pass
            
            email = pod.metadata.annotations.get("amd-oneclick/email", "unknown")
            github_path = pod.metadata.annotations.get("amd-oneclick/github-path")
            
            return {
                "id": instance_id,
                "email": email,
                "pod_name": pod.metadata.name,
                "service_name": f"notebook-{instance_id}",
                "image": pod.spec.containers[0].image,
                "status": pod.status.phase.lower(),
                "created_at": pod.metadata.creation_timestamp,
                "url": self._build_url(instance_id, github_path) if service_exists else None,
                "github_org": pod.metadata.annotations.get("amd-oneclick/github-org"),
                "github_repo": pod.metadata.annotations.get("amd-oneclick/github-repo"),
                "github_path": github_path,
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def delete_instance_by_id(self, instance_id: str) -> bool:
        """Delete a notebook instance by instance ID"""
        deleted = False
        
        # Delete Service (new naming: notebook-{instance_id})
        try:
            self.core_v1.delete_namespaced_service(
                name=f"notebook-{instance_id}",
                namespace=self.namespace
            )
            logger.info(f"Deleted service notebook-{instance_id}")
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Error deleting service: {e}")
        
        # Also try to delete old-style service name for backwards compatibility
        try:
            self.core_v1.delete_namespaced_service(
                name=f"{instance_id}-svc",
                namespace=self.namespace
            )
            logger.info(f"Deleted legacy service {instance_id}-svc")
            deleted = True
        except ApiException as e:
            pass  # Ignore if not found
        
        # Delete Pod
        try:
            self.core_v1.delete_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
            logger.info(f"Deleted pod {instance_id}")
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Error deleting pod: {e}")
        
        return deleted
    
    def delete_instance(self, email: str) -> bool:
        """Delete a notebook instance"""
        instance_id = self._generate_instance_id(email)
        return self.delete_instance_by_id(instance_id)
    
    def list_instances(self) -> list:
        """List all notebook instances"""
        instances = []
        
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app={settings.NOTEBOOK_LABEL_PREFIX}"
            )
            
            for pod in pods.items:
                instance_id = pod.metadata.labels.get("instance-id", "unknown")
                email = pod.metadata.annotations.get("amd-oneclick/email", "unknown")
                created_at = pod.metadata.creation_timestamp
                
                # Get GitHub info from annotations
                github_org = pod.metadata.annotations.get("amd-oneclick/github-org")
                github_repo = pod.metadata.annotations.get("amd-oneclick/github-repo")
                github_path = pod.metadata.annotations.get("amd-oneclick/github-path")
                
                # Check if service exists
                service_exists = False
                try:
                    self.core_v1.read_namespaced_service(
                        name=f"notebook-{instance_id}",
                        namespace=self.namespace
                    )
                    service_exists = True
                except ApiException:
                    pass
                
                # Calculate uptime
                uptime_minutes = 0
                if created_at:
                    uptime_delta = datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)
                    uptime_minutes = int(uptime_delta.total_seconds() / 60)
                
                instances.append({
                    "id": instance_id,
                    "email": email,
                    "pod_name": pod.metadata.name,
                    "service_name": f"notebook-{instance_id}",
                    "image": pod.spec.containers[0].image if pod.spec.containers else "unknown",
                    "status": pod.status.phase.lower() if pod.status.phase else "unknown",
                    "created_at": created_at.isoformat() if created_at else None,
                    "url": self._build_url(instance_id, github_path) if service_exists else None,
                    "uptime_minutes": uptime_minutes,
                    "github_org": github_org,
                    "github_repo": github_repo,
                    "github_path": github_path,
                })
        except ApiException as e:
            logger.error(f"Error listing pods: {e}")
        
        return instances
    
    def delete_all_instances(self) -> int:
        """Delete all notebook instances"""
        instances = self.list_instances()
        deleted_count = 0
        
        for instance in instances:
            # Use instance ID directly, not email (GitHub instances have fake emails)
            if self.delete_instance_by_id(instance["id"]):
                deleted_count += 1
        
        return deleted_count
    
    def get_pod_status(self, email: str, instance_id: Optional[str] = None) -> Optional[str]:
        """Get the current status of a pod"""
        if not instance_id:
            instance_id = self._generate_instance_id(email)
        
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
            
            phase = pod.status.phase.lower() if pod.status.phase else "unknown"
            
            # Check container statuses for more detail
            if pod.status.container_statuses:
                container_status = pod.status.container_statuses[0]
                if container_status.ready:
                    # Container is ready, but we need to verify Jupyter is actually responding
                    if self._check_jupyter_ready(instance_id):
                        return "ready"
                    else:
                        return "jupyter_starting"
                elif container_status.state.waiting:
                    reason = container_status.state.waiting.reason or "waiting"
                    if reason in ["ContainerCreating", "PodInitializing"]:
                        return "initializing"
                    elif reason == "ImagePullBackOff":
                        return "failed"
                    return "loading"
                elif container_status.state.running:
                    # Container is running but not ready yet
                    return "running"
            
            return phase
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def _check_jupyter_ready(self, instance_id: str, timeout: float = 2.0) -> bool:
        """Check if Jupyter is responding via ClusterIP service"""
        try:
            # Try to connect to the Jupyter server via ClusterIP service
            # Service DNS: notebook-{instance_id}.default.svc.cluster.local
            service_host = f"notebook-{instance_id}.{self.namespace}.svc.cluster.local"
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((service_host, settings.NOTEBOOK_PORT))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"Jupyter health check failed for {instance_id}: {e}")
            return False
    
    def check_pod_activity(self, email: str) -> Optional[datetime]:
        """Check last activity of a pod by examining logs"""
        instance_id = self._generate_instance_id(email)
        
        try:
            # Get recent logs
            logs = self.core_v1.read_namespaced_pod_log(
                name=instance_id,
                namespace=self.namespace,
                tail_lines=10,
                timestamps=True
            )
            
            if logs:
                # Parse last log timestamp
                lines = logs.strip().split('\n')
                if lines:
                    last_line = lines[-1]
                    # Kubernetes log format: 2024-01-01T00:00:00.000000000Z ...
                    timestamp_str = last_line.split(' ')[0]
                    try:
                        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    except ValueError:
                        pass
            
            return None
        except ApiException:
            return None
    
    def cleanup_idle_instances(self) -> list:
        """Cleanup idle and expired instances"""
        cleaned = []
        instances = self.list_instances()
        now = datetime.now(timezone.utc)
        
        for instance in instances:
            should_delete = False
            reason = ""
            
            # Check max lifetime
            uptime_hours = instance["uptime_minutes"] / 60
            if uptime_hours >= settings.MAX_LIFETIME_HOURS:
                should_delete = True
                reason = f"exceeded max lifetime ({settings.MAX_LIFETIME_HOURS}h)"
            
            # Check idle timeout (only for running instances)
            elif instance["status"] == "running":
                last_activity = self.check_pod_activity(instance["email"])
                if last_activity:
                    idle_minutes = (now - last_activity).total_seconds() / 60
                    if idle_minutes >= settings.IDLE_TIMEOUT_MINUTES:
                        should_delete = True
                        reason = f"idle for {int(idle_minutes)} minutes"
            
            if should_delete:
                # Use instance ID directly, not email (GitHub instances have fake emails)
                if self.delete_instance_by_id(instance["id"]):
                    cleaned.append({
                        "id": instance["id"],
                        "email": instance["email"],
                        "reason": reason
                    })
                    logger.info(f"Cleaned up instance {instance['id']}: {reason}")
        
        return cleaned
    
    # =========================================================================
    # Space Management Methods
    # =========================================================================
    
    def _get_space_pod_manifest(self, space_id: str, request: SpaceRequest,
                                resource_spec: ResourceSpec) -> dict:
        """Generate Pod manifest for a Space instance"""
        labels = self._get_space_labels(space_id, request.src_meta, resource_spec)
        
        # Build annotations
        annotations = {
            "amd-oneclick/type": "space",
            "amd-oneclick/created-at": datetime.now(timezone.utc).isoformat(),
            "amd-oneclick/src": request.src_meta.src,
            "amd-oneclick/src-email": request.src_meta.outer_email or "",
            "amd-oneclick/src-uid": request.src_meta.inner_uid or "",
            "amd-oneclick/repo-url": request.repo_url,
            "amd-oneclick/start-command": request.start_command,
            "amd-oneclick/branch": request.branch,
        }
        
        # Determine Docker image
        image = request.docker_image
        if not image:
            image = getattr(settings, 'DEFAULT_SPACE_IMAGE', 
                          getattr(settings, 'DEFAULT_IMAGE', 'rocm/vllm-dev:nightly_main_20260125'))
        elif hasattr(settings, 'get_image_url'):
            image = settings.get_image_url(image) or image
        
        # Determine exposed port
        exposed_port = request.custom_port or getattr(settings, 'SPACE_DEFAULT_PORT', 7860)
        
        # Build environment variables
        env_vars = [
            {"name": "SHELL", "value": "/bin/bash"},
            {"name": "SPACE_ID", "value": space_id},
            {"name": "REPO_URL", "value": request.repo_url},
            {"name": "REPO_BRANCH", "value": request.branch},
            {"name": "START_COMMAND", "value": request.start_command},
            {"name": "EXPOSED_PORT", "value": str(exposed_port)},
        ]
        
        # Add conda env if specified
        if request.conda_env:
            conda_url = ""
            if hasattr(settings, 'get_conda_env_url'):
                conda_url = settings.get_conda_env_url(request.conda_env) or ""
            env_vars.append({"name": "CONDA_ENV", "value": request.conda_env})
            env_vars.append({"name": "CONDA_ENV_URL", "value": conda_url})
        
        # Add custom environment variables
        if request.env_vars:
            for key, value in request.env_vars.items():
                env_vars.append({"name": key, "value": value})
        
        # Build startup script for Space
        startup_script = """#!/bin/bash
set -e

echo "=== AMD OneClick Space Startup ==="
echo "Space ID: ${SPACE_ID}"
echo "Repository: ${REPO_URL}"
echo "Branch: ${REPO_BRANCH}"

# Create workspace directory
mkdir -p /workspace
cd /workspace

# Remove existing app directory if it exists
if [ -d "app" ]; then
    echo "Removing existing app directory..."
    rm -rf app
fi

# Clone the repository
echo "Cloning repository..."
git clone --depth 1 -b "${REPO_BRANCH}" "${REPO_URL}" app || {
    echo "Failed to clone with branch, trying default branch..."
    git clone --depth 1 "${REPO_URL}" app
}
cd app

# Download and setup conda environment if specified
if [ -n "${CONDA_ENV_URL}" ]; then
    echo "Downloading conda environment from ${CONDA_ENV_URL}..."
    mkdir -p /opt/conda_envs
    wget -q -O /tmp/conda_env.tar.gz "${CONDA_ENV_URL}" || echo "Warning: Failed to download conda env"
    if [ -f /tmp/conda_env.tar.gz ]; then
        tar -xzf /tmp/conda_env.tar.gz -C /opt/conda_envs
        export PATH="/opt/conda_envs/${CONDA_ENV}/bin:${PATH}"
        echo "Conda environment ${CONDA_ENV} activated"
    fi
fi

# Try to read Gradio version from README.md (HuggingFace Spaces format)
GRADIO_VERSION=""
if [ -f README.md ]; then
    echo "DEBUG: README.md exists, checking content..."
    echo "DEBUG: First 10 lines of README.md:"
    head -10 README.md
    # Use grep and awk for maximum compatibility
    GRADIO_VERSION=$(grep '^sdk_version:' README.md | awk -F: '{gsub(/[[:space:]]/,"",$2); print $2}' | head -1)
    echo "DEBUG: Extracted GRADIO_VERSION='${GRADIO_VERSION}'"
    if [ -n "${GRADIO_VERSION}" ]; then
        echo "Found SDK version in README: ${GRADIO_VERSION}"
    else
        echo "No SDK version found in README"
    fi
else
    echo "DEBUG: README.md not found in $(pwd)"
    ls -la
fi

# Install requirements if exists
if [ -f requirements.txt ]; then
    echo "Installing requirements..."
    # First, install Gradio with the version from README or default
    echo "Installing Gradio..."
    if [ -n "${GRADIO_VERSION}" ]; then
        pip install "gradio==${GRADIO_VERSION}" spaces --quiet 2>/dev/null || pip install gradio spaces --quiet 2>/dev/null || true
    else
        pip install gradio spaces --quiet 2>/dev/null || true
    fi
    
    # Install each package separately to continue even if some fail
    # Skip packages with platform-specific wheels that won't work on ROCm
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Trim whitespace
        line=$(echo "$line" | xargs)
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        # Skip CUDA-specific packages that won't work on ROCm
        if [[ "$line" =~ "cu1" ]] || [[ "$line" =~ "flash_attn" ]] || [[ "$line" =~ "flash-attn" ]]; then
            echo "Skipping CUDA-specific package: $line"
            continue
        fi
        echo "Installing: $line"
        pip install "$line" --quiet 2>/dev/null || echo "Warning: Failed to install $line"
    done < requirements.txt
    echo "Requirements installation completed"
else
    # No requirements.txt, but install common Space dependencies
    echo "Installing Gradio..."
    if [ -n "${GRADIO_VERSION}" ]; then
        pip install "gradio==${GRADIO_VERSION}" spaces --quiet 2>/dev/null || pip install gradio spaces --quiet 2>/dev/null || true
    else
        pip install gradio spaces --quiet 2>/dev/null || true
    fi
fi

# Run the start command
echo "Starting application with: ${START_COMMAND}"
exec ${START_COMMAND}
"""
        
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": space_id,
                "namespace": self.namespace,
                "labels": labels,
                "annotations": annotations
            },
            "spec": {
                "tolerations": self._build_tolerations(resource_spec),
                "nodeSelector": self._build_node_selector(resource_spec),
                "containers": [
                    {
                        "name": "space",
                        "image": image,
                        "imagePullPolicy": "Always",
                        "command": ["/bin/bash", "-c"],
                        "args": [startup_script],
                        "ports": [
                            {
                                "containerPort": exposed_port,
                                "name": "app"
                            }
                        ],
                        "resources": self._build_resource_requirements(resource_spec),
                        "env": env_vars,
                        "volumeMounts": [
                            {"name": "shm", "mountPath": "/dev/shm"},
                            {"name": "workspace", "mountPath": "/workspace"}
                        ]
                    }
                ],
                "volumes": [
                    {
                        "name": "shm",
                        "emptyDir": {
                            "medium": "Memory",
                            "sizeLimit": "64Gi"
                        }
                    },
                    {
                        "name": "workspace",
                        "emptyDir": {
                            "sizeLimit": resource_spec.storage
                        }
                    }
                ],
                "restartPolicy": "Always"
            }
        }
    
    def _get_space_service_manifest(self, space_id: str, request: SpaceRequest,
                                    resource_spec: ResourceSpec) -> dict:
        """Generate Service manifest for a Space instance"""
        labels = self._get_space_labels(space_id, request.src_meta, resource_spec)
        exposed_port = request.custom_port or getattr(settings, 'SPACE_DEFAULT_PORT', 7860)
        
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"space-{space_id}",
                "namespace": self.namespace,
                "labels": labels,
            },
            "spec": {
                "selector": labels,
                "type": "ClusterIP",
                "ports": [
                    {
                        "name": "app",
                        "port": exposed_port,
                        "targetPort": exposed_port
                    }
                ]
            }
        }
    
    def _build_space_url(self, space_id: str, port: int = None) -> str:
        """Build Space URL via Nginx proxy"""
        protocol = "https" if not settings.SERVICE_HOST.replace(".", "").isdigit() else "http"
        return f"{protocol}://{settings.SERVICE_HOST}/space/{space_id}/"
    
    def create_space(self, request: SpaceRequest) -> dict:
        """Create a new Space instance"""
        # Generate space ID
        space_id = self._generate_space_id(request.repo_url, request.src_meta)
        
        # Get resource spec from preset
        resource_spec = self._get_resource_spec_from_preset(request.resource_preset)
        
        # Check if space already exists
        existing = self.get_space(space_id)
        if existing:
            return existing
        
        # Create Pod
        pod_manifest = self._get_space_pod_manifest(space_id, request, resource_spec)
        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created Space pod {space_id}")
        except ApiException as e:
            logger.error(f"Failed to create Space pod: {e}")
            raise
        
        # Create Service
        svc_manifest = self._get_space_service_manifest(space_id, request, resource_spec)
        try:
            self.core_v1.create_namespaced_service(
                namespace=self.namespace,
                body=svc_manifest
            )
            logger.info(f"Created Space service space-{space_id}")
        except ApiException as e:
            logger.error(f"Failed to create Space service: {e}")
            self.delete_space(space_id)
            raise
        
        exposed_port = request.custom_port or getattr(settings, 'SPACE_DEFAULT_PORT', 7860)
        
        return {
            "id": space_id,
            "repo_url": request.repo_url,
            "start_command": request.start_command,
            "src_meta": request.src_meta.model_dump(),
            "resource_spec": resource_spec.model_dump(),
            "status": "pending",
            "url": self._build_space_url(space_id, exposed_port),
            "created_at": datetime.now(timezone.utc),
            "docker_image": pod_manifest["spec"]["containers"][0]["image"],
            "conda_env": request.conda_env,
            "custom_port": exposed_port,
            "env_vars": request.env_vars,
            "branch": request.branch,
        }
    
    def get_space(self, space_id: str) -> Optional[dict]:
        """Get Space instance by ID"""
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=space_id,
                namespace=self.namespace
            )
            
            # Verify it's a space
            if pod.metadata.labels.get("instance-type") != "space":
                return None
            
            # Check if service exists
            service_exists = False
            try:
                self.core_v1.read_namespaced_service(
                    name=f"space-{space_id}",
                    namespace=self.namespace
                )
                service_exists = True
            except ApiException:
                pass
            
            annotations = pod.metadata.annotations or {}
            
            return {
                "id": space_id,
                "repo_url": annotations.get("amd-oneclick/repo-url", ""),
                "start_command": annotations.get("amd-oneclick/start-command", ""),
                "src": annotations.get("amd-oneclick/src", ""),
                "src_email": annotations.get("amd-oneclick/src-email", ""),
                "src_uid": annotations.get("amd-oneclick/src-uid", ""),
                "status": pod.status.phase.lower() if pod.status.phase else "unknown",
                "created_at": pod.metadata.creation_timestamp,
                "url": self._build_space_url(space_id) if service_exists else None,
                "branch": annotations.get("amd-oneclick/branch", "main"),
                "gpu_type": pod.metadata.labels.get("gpu-type", "unknown"),
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def delete_space(self, space_id: str) -> bool:
        """Delete a Space instance"""
        deleted = False
        
        # Delete Service
        try:
            self.core_v1.delete_namespaced_service(
                name=f"space-{space_id}",
                namespace=self.namespace
            )
            logger.info(f"Deleted Space service space-{space_id}")
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Error deleting Space service: {e}")
        
        # Delete Pod
        try:
            self.core_v1.delete_namespaced_pod(
                name=space_id,
                namespace=self.namespace
            )
            logger.info(f"Deleted Space pod {space_id}")
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Error deleting Space pod: {e}")
        
        return deleted
    
    def list_spaces(self) -> list:
        """List all Space instances"""
        spaces = []
        label_prefix = getattr(settings, 'SPACE_LABEL_PREFIX', 'amd-oneclick-space')
        
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app={label_prefix}"
            )
            
            for pod in pods.items:
                space_id = pod.metadata.labels.get("instance-id", "unknown")
                annotations = pod.metadata.annotations or {}
                created_at = pod.metadata.creation_timestamp
                
                # Check if service exists
                service_exists = False
                try:
                    self.core_v1.read_namespaced_service(
                        name=f"space-{space_id}",
                        namespace=self.namespace
                    )
                    service_exists = True
                except ApiException:
                    pass
                
                # Calculate uptime
                uptime_minutes = 0
                if created_at:
                    uptime_delta = datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)
                    uptime_minutes = int(uptime_delta.total_seconds() / 60)
                
                spaces.append({
                    "id": space_id,
                    "repo_url": annotations.get("amd-oneclick/repo-url", ""),
                    "start_command": annotations.get("amd-oneclick/start-command", ""),
                    "src": annotations.get("amd-oneclick/src", ""),
                    "src_email": annotations.get("amd-oneclick/src-email", ""),
                    "status": pod.status.phase.lower() if pod.status.phase else "unknown",
                    "created_at": created_at.isoformat() if created_at else None,
                    "url": self._build_space_url(space_id) if service_exists else None,
                    "uptime_minutes": uptime_minutes,
                    "gpu_type": pod.metadata.labels.get("gpu-type", "unknown"),
                    "gpu_count": 1,  # TODO: Extract from resource spec
                })
        except ApiException as e:
            logger.error(f"Error listing Spaces: {e}")
        
        return spaces
    
    def get_space_status(self, space_id: str) -> Optional[str]:
        """Get Space pod status"""
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=space_id,
                namespace=self.namespace
            )
            
            phase = pod.status.phase.lower() if pod.status.phase else "unknown"
            
            if pod.status.container_statuses:
                container_status = pod.status.container_statuses[0]
                if container_status.ready:
                    return "ready"
                elif container_status.state.waiting:
                    reason = container_status.state.waiting.reason or "waiting"
                    if reason in ["ContainerCreating", "PodInitializing"]:
                        return "initializing"
                    elif reason == "ImagePullBackOff":
                        return "failed"
                    return "loading"
                elif container_status.state.running:
                    return "running"
            
            return phase
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def get_space_logs(self, space_id: str, tail_lines: int = 100) -> Optional[str]:
        """Get Space pod logs"""
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=space_id,
                namespace=self.namespace,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            if e.status == 404:
                return None
            logger.error(f"Error getting Space logs: {e}")
            return None
    
    def fork_space(self, space_id: str, new_src_meta: SrcMeta,
                   new_resource_preset: Optional[str] = None) -> Optional[dict]:
        """Fork an existing Space to create a new instance"""
        # Get original space
        original = self.get_space(space_id)
        if not original:
            return None
        
        # Get original pod for full configuration
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=space_id,
                namespace=self.namespace
            )
        except ApiException:
            return None
        
        annotations = pod.metadata.annotations or {}
        
        # Build new request with original config + new src_meta
        request = SpaceRequest(
            repo_url=original["repo_url"],
            start_command=original["start_command"],
            src_meta=new_src_meta,
            resource_preset=new_resource_preset or "mi300x-1",
            branch=original.get("branch", "main"),
        )
        
        # Create new space (will get unique ID based on new src_meta)
        return self.create_space(request)
    
    # =========================================================================
    # Generic Notebook Methods
    # =========================================================================
    
    def _get_generic_notebook_pod_manifest(self, instance_id: str, 
                                           request: GenericNotebookRequest,
                                           resource_spec: ResourceSpec) -> dict:
        """Generate Pod manifest for a generic Notebook instance"""
        labels = self._get_generic_notebook_labels(instance_id, request.src_meta, resource_spec)
        
        # Build annotations
        annotations = {
            "amd-oneclick/type": "notebook",
            "amd-oneclick/created-at": datetime.now(timezone.utc).isoformat(),
            "amd-oneclick/src": request.src_meta.src,
            "amd-oneclick/src-email": request.src_meta.outer_email or "",
            "amd-oneclick/src-uid": request.src_meta.inner_uid or "",
            "amd-oneclick/notebook-url": request.notebook_url,
        }
        
        # Determine Docker image
        image = request.docker_image
        if not image:
            image = getattr(settings, 'DEFAULT_NOTEBOOK_IMAGE',
                          getattr(settings, 'DEFAULT_IMAGE', 'rocm/vllm-dev:nightly_main_20260125'))
        elif hasattr(settings, 'get_image_url'):
            image = settings.get_image_url(image) or image
        
        # Build environment variables
        env_vars = [
            {"name": "SHELL", "value": "/bin/bash"},
            {"name": "INSTANCE_ID", "value": instance_id},
            {"name": "NOTEBOOK_URL", "value": request.notebook_url},
            {"name": "NOTEBOOK_TOKEN", "value": settings.NOTEBOOK_TOKEN},
            {"name": "JUPYTER_PORT", "value": str(settings.NOTEBOOK_PORT)},
        ]
        
        # Add conda env if specified
        if request.conda_env:
            conda_url = ""
            if hasattr(settings, 'get_conda_env_url'):
                conda_url = settings.get_conda_env_url(request.conda_env) or ""
            env_vars.append({"name": "CONDA_ENV", "value": request.conda_env})
            env_vars.append({"name": "CONDA_ENV_URL", "value": conda_url})
        
        # Build startup script for generic notebook
        startup_script = """#!/bin/bash
set -e

echo "=== AMD OneClick Notebook Startup ==="
echo "Instance ID: ${INSTANCE_ID}"
echo "Notebook URL: ${NOTEBOOK_URL}"

# Install Jupyter if not already installed
if ! command -v jupyter &> /dev/null; then
    echo "Installing JupyterLab..."
    pip install jupyterlab -q
fi

# Create notebook directory
mkdir -p /workspace/notebooks
cd /workspace/notebooks

# Download notebook if URL provided
if [ -n "${NOTEBOOK_URL}" ]; then
    echo "Downloading notebook..."
    NOTEBOOK_FILENAME=$(basename "${NOTEBOOK_URL}")
    wget -q -O "${NOTEBOOK_FILENAME}" "${NOTEBOOK_URL}" || echo "Warning: Failed to download notebook"
fi

# Download and setup conda environment if specified
if [ -n "${CONDA_ENV_URL}" ]; then
    echo "Downloading conda environment from ${CONDA_ENV_URL}..."
    mkdir -p /opt/conda_envs
    wget -q -O /tmp/conda_env.tar.gz "${CONDA_ENV_URL}" || echo "Warning: Failed to download conda env"
    if [ -f /tmp/conda_env.tar.gz ]; then
        tar -xzf /tmp/conda_env.tar.gz -C /opt/conda_envs
        export PATH="/opt/conda_envs/${CONDA_ENV}/bin:${PATH}"
        echo "Conda environment ${CONDA_ENV} activated"
    fi
fi

# Determine base URL based on instance ID
BASE_URL="/instance/${INSTANCE_ID}/"

echo "Starting Jupyter Lab..."
exec jupyter lab \
    --ip=0.0.0.0 \
    --port=${JUPYTER_PORT:-8888} \
    --no-browser \
    --allow-root \
    --ServerApp.token="${NOTEBOOK_TOKEN}" \
    --ServerApp.base_url="${BASE_URL}" \
    --notebook-dir=/workspace/notebooks
"""
        
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": instance_id,
                "namespace": self.namespace,
                "labels": labels,
                "annotations": annotations
            },
            "spec": {
                "tolerations": self._build_tolerations(resource_spec),
                "nodeSelector": self._build_node_selector(resource_spec),
                "containers": [
                    {
                        "name": "notebook",
                        "image": image,
                        "imagePullPolicy": "Always",
                        "command": ["/bin/bash", "-c"],
                        "args": [startup_script],
                        "ports": [
                            {
                                "containerPort": settings.NOTEBOOK_PORT,
                                "name": "jupyter"
                            }
                        ],
                        "resources": self._build_resource_requirements(resource_spec),
                        "env": env_vars,
                        "volumeMounts": [
                            {"name": "shm", "mountPath": "/dev/shm"},
                            {"name": "workspace", "mountPath": "/workspace"}
                        ]
                    }
                ],
                "volumes": [
                    {
                        "name": "shm",
                        "emptyDir": {
                            "medium": "Memory",
                            "sizeLimit": "64Gi"
                        }
                    },
                    {
                        "name": "workspace",
                        "emptyDir": {
                            "sizeLimit": resource_spec.storage
                        }
                    }
                ],
                "restartPolicy": "Always"
            }
        }
    
    def create_generic_notebook(self, request: GenericNotebookRequest) -> dict:
        """Create a new generic Notebook instance"""
        # Generate unique instance ID
        instance_id = self._generate_notebook_id()
        
        # Get resource spec from preset
        resource_spec = self._get_resource_spec_from_preset(request.resource_preset)
        
        # Create Pod
        pod_manifest = self._get_generic_notebook_pod_manifest(instance_id, request, resource_spec)
        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created generic notebook pod {instance_id}")
        except ApiException as e:
            logger.error(f"Failed to create generic notebook pod: {e}")
            raise
        
        # Create Service
        labels = self._get_generic_notebook_labels(instance_id, request.src_meta, resource_spec)
        svc_manifest = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"notebook-{instance_id}",
                "namespace": self.namespace,
                "labels": labels,
            },
            "spec": {
                "selector": labels,
                "type": "ClusterIP",
                "ports": [
                    {
                        "name": "jupyter",
                        "port": settings.NOTEBOOK_PORT,
                        "targetPort": settings.NOTEBOOK_PORT
                    }
                ]
            }
        }
        
        try:
            self.core_v1.create_namespaced_service(
                namespace=self.namespace,
                body=svc_manifest
            )
            logger.info(f"Created generic notebook service notebook-{instance_id}")
        except ApiException as e:
            logger.error(f"Failed to create generic notebook service: {e}")
            self.delete_instance_by_id(instance_id)
            raise
        
        return {
            "id": instance_id,
            "notebook_url": request.notebook_url,
            "src_meta": request.src_meta.model_dump(),
            "resource_spec": resource_spec.model_dump(),
            "status": "pending",
            "url": self._build_url(instance_id),
            "created_at": datetime.now(timezone.utc),
            "docker_image": pod_manifest["spec"]["containers"][0]["image"],
            "conda_env": request.conda_env,
        }
    
    def fork_notebook(self, instance_id: str, new_src_meta: SrcMeta,
                      new_resource_preset: Optional[str] = None) -> Optional[dict]:
        """Fork an existing Notebook to create a new instance"""
        # Get original instance
        original = self.get_instance_by_id(instance_id)
        if not original:
            return None
        
        # Get original pod for full configuration
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
        except ApiException:
            return None
        
        annotations = pod.metadata.annotations or {}
        notebook_url = annotations.get("amd-oneclick/notebook-url", "")
        
        if not notebook_url:
            # Legacy notebook without URL - cannot fork
            logger.warning(f"Cannot fork legacy notebook {instance_id} without notebook URL")
            return None
        
        # Build new request
        request = GenericNotebookRequest(
            notebook_url=notebook_url,
            src_meta=new_src_meta,
            resource_preset=new_resource_preset or "mi300x-1",
        )
        
        return self.create_generic_notebook(request)
    
    # =========================================================================
    # Cleanup Methods (Extended)
    # =========================================================================
    
    def cleanup_all_idle(self) -> dict:
        """Cleanup both idle notebooks and spaces"""
        result = {
            "notebooks": self.cleanup_idle_instances(),
            "spaces": self.cleanup_idle_spaces()
        }
        return result
    
    def cleanup_idle_spaces(self) -> list:
        """Cleanup idle and expired Space instances"""
        cleaned = []
        spaces = self.list_spaces()
        now = datetime.now(timezone.utc)
        
        for space in spaces:
            should_delete = False
            reason = ""
            
            # Check max lifetime
            uptime_hours = space["uptime_minutes"] / 60
            if uptime_hours >= settings.MAX_LIFETIME_HOURS:
                should_delete = True
                reason = f"exceeded max lifetime ({settings.MAX_LIFETIME_HOURS}h)"
            
            if should_delete:
                if self.delete_space(space["id"]):
                    cleaned.append({
                        "id": space["id"],
                        "repo_url": space["repo_url"],
                        "reason": reason
                    })
                    logger.info(f"Cleaned up Space {space['id']}: {reason}")
        
        return cleaned
    
    def delete_all_spaces(self) -> int:
        """Delete all Space instances"""
        spaces = self.list_spaces()
        deleted_count = 0
        
        for space in spaces:
            if self.delete_space(space["id"]):
                deleted_count += 1
        
        return deleted_count


# Global K8s client instance
k8s_client = K8sClient()
