"""
Kubernetes client for managing notebook instances
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .config import settings

logger = logging.getLogger(__name__)


class K8sClient:
    """Kubernetes client for notebook management"""
    
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
    
    def _generate_instance_id(self, email: str) -> str:
        """Generate a unique instance ID from email"""
        hash_str = hashlib.md5(email.lower().encode()).hexdigest()[:8]
        return f"nb-{hash_str}"
    
    def _get_labels(self, email: str, instance_id: str) -> dict:
        """Generate labels for K8s resources"""
        return {
            "app": settings.NOTEBOOK_LABEL_PREFIX,
            "instance-id": instance_id,
            "email-hash": hashlib.md5(email.lower().encode()).hexdigest()[:16],
        }
    
    def _get_pod_manifest(self, email: str, instance_id: str, image: str) -> dict:
        """Generate Pod manifest"""
        labels = self._get_labels(email, instance_id)
        
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": instance_id,
                "namespace": self.namespace,
                "labels": labels,
                "annotations": {
                    "amd-oneclick/email": email,
                    "amd-oneclick/created-at": datetime.now(timezone.utc).isoformat(),
                }
            },
            "spec": {
                "nodeName": settings.K8S_NODE_NAME,
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
                        "imagePullPolicy": "IfNotPresent",
                        "command": ["/bin/bash", "-c"],
                        "args": [
                            f"""
echo "{settings.PYPI_HOST_IP} {settings.PYPI_HOST}" >> /etc/hosts
mkdir -p ~/.pip
cat > ~/.pip/pip.conf << EOF
[global]
index-url = {settings.PYPI_MIRROR}
trusted-host = {settings.PYPI_HOST}
EOF
pip install --no-cache-dir jupyter ihighlight
cd /app
jupyter lab --ip=0.0.0.0 --port={settings.NOTEBOOK_PORT} --no-browser --allow-root --ServerApp.token='{settings.NOTEBOOK_TOKEN}'
"""
                        ],
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
                            {"name": "USER_EMAIL", "value": email}
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
    
    def _get_service_manifest(self, email: str, instance_id: str, node_port: int) -> dict:
        """Generate Service manifest"""
        labels = self._get_labels(email, instance_id)
        
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{instance_id}-svc",
                "namespace": self.namespace,
                "labels": labels,
            },
            "spec": {
                "selector": labels,
                "type": "NodePort",
                "ports": [
                    {
                        "name": "jupyter",
                        "port": settings.NOTEBOOK_PORT,
                        "targetPort": settings.NOTEBOOK_PORT,
                        "nodePort": node_port
                    }
                ]
            }
        }
    
    def _allocate_node_port(self) -> int:
        """Allocate an available NodePort"""
        used_ports = set()
        
        try:
            services = self.core_v1.list_namespaced_service(
                namespace=self.namespace,
                label_selector=f"app={settings.NOTEBOOK_LABEL_PREFIX}"
            )
            for svc in services.items:
                for port in svc.spec.ports or []:
                    if port.node_port:
                        used_ports.add(port.node_port)
        except ApiException as e:
            logger.warning(f"Error listing services: {e}")
        
        # Find available port starting from base
        port = settings.NODE_PORT_BASE
        while port in used_ports and port < 32767:
            port += 1
        
        return port
    
    def get_instance_by_email(self, email: str) -> Optional[dict]:
        """Get existing notebook instance for an email"""
        instance_id = self._generate_instance_id(email)
        
        try:
            pod = self.core_v1.read_namespaced_pod(
                name=instance_id,
                namespace=self.namespace
            )
            
            # Get associated service
            try:
                svc = self.core_v1.read_namespaced_service(
                    name=f"{instance_id}-svc",
                    namespace=self.namespace
                )
                node_port = svc.spec.ports[0].node_port if svc.spec.ports else None
            except ApiException:
                node_port = None
            
            return {
                "id": instance_id,
                "email": email,
                "pod_name": pod.metadata.name,
                "service_name": f"{instance_id}-svc",
                "image": pod.spec.containers[0].image,
                "status": pod.status.phase.lower(),
                "created_at": pod.metadata.creation_timestamp,
                "node_port": node_port,
                "url": self._build_url(node_port) if node_port else None
            }
        except ApiException as e:
            if e.status == 404:
                return None
            raise
    
    def _build_url(self, node_port: int) -> str:
        """Build notebook URL"""
        return f"http://{settings.SERVICE_HOST}:{node_port}/lab?token={settings.NOTEBOOK_TOKEN}"
    
    def create_instance(self, email: str, image: Optional[str] = None) -> dict:
        """Create a new notebook instance"""
        instance_id = self._generate_instance_id(email)
        image = image or settings.DEFAULT_IMAGE
        
        # Check if instance already exists
        existing = self.get_instance_by_email(email)
        if existing:
            return existing
        
        # Allocate NodePort
        node_port = self._allocate_node_port()
        
        # Create Pod
        pod_manifest = self._get_pod_manifest(email, instance_id, image)
        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.namespace,
                body=pod_manifest
            )
            logger.info(f"Created pod {instance_id} for {email}")
        except ApiException as e:
            logger.error(f"Failed to create pod: {e}")
            raise
        
        # Create Service
        svc_manifest = self._get_service_manifest(email, instance_id, node_port)
        try:
            self.core_v1.create_namespaced_service(
                namespace=self.namespace,
                body=svc_manifest
            )
            logger.info(f"Created service {instance_id}-svc with NodePort {node_port}")
        except ApiException as e:
            logger.error(f"Failed to create service: {e}")
            # Cleanup pod if service creation fails
            self.delete_instance(email)
            raise
        
        return {
            "id": instance_id,
            "email": email,
            "pod_name": instance_id,
            "service_name": f"{instance_id}-svc",
            "image": image,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "node_port": node_port,
            "url": self._build_url(node_port)
        }
    
    def delete_instance(self, email: str) -> bool:
        """Delete a notebook instance"""
        instance_id = self._generate_instance_id(email)
        deleted = False
        
        # Delete Service
        try:
            self.core_v1.delete_namespaced_service(
                name=f"{instance_id}-svc",
                namespace=self.namespace
            )
            logger.info(f"Deleted service {instance_id}-svc")
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Error deleting service: {e}")
        
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
                
                # Get NodePort from service
                node_port = None
                try:
                    svc = self.core_v1.read_namespaced_service(
                        name=f"{instance_id}-svc",
                        namespace=self.namespace
                    )
                    node_port = svc.spec.ports[0].node_port if svc.spec.ports else None
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
                    "service_name": f"{instance_id}-svc",
                    "image": pod.spec.containers[0].image if pod.spec.containers else "unknown",
                    "status": pod.status.phase.lower() if pod.status.phase else "unknown",
                    "created_at": created_at.isoformat() if created_at else None,
                    "node_port": node_port,
                    "url": self._build_url(node_port) if node_port else None,
                    "uptime_minutes": uptime_minutes
                })
        except ApiException as e:
            logger.error(f"Error listing pods: {e}")
        
        return instances
    
    def delete_all_instances(self) -> int:
        """Delete all notebook instances"""
        instances = self.list_instances()
        deleted_count = 0
        
        for instance in instances:
            if self.delete_instance(instance["email"]):
                deleted_count += 1
        
        return deleted_count
    
    def get_pod_status(self, email: str) -> Optional[str]:
        """Get the current status of a pod"""
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
                if self.delete_instance(instance["email"]):
                    cleaned.append({
                        "email": instance["email"],
                        "reason": reason
                    })
                    logger.info(f"Cleaned up instance for {instance['email']}: {reason}")
        
        return cleaned


# Global K8s client instance
k8s_client = K8sClient()
