"""
Service control API endpoints.

Provides endpoints to manage service lifecycle via Docker API.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.docker.manager import get_docker_manager

router = APIRouter()


class ServiceAction(BaseModel):
    """Service action request."""

    timeout: int = 10


@router.get("/")
async def list_services(current_user: User = Depends(get_current_user)):
    """
    List all quant-vibe services with their status.

    Args:
        current_user: Authenticated user

    Returns:
        List of services with status information
    """
    manager = get_docker_manager()
    services = manager.list_services()

    return {
        "services": services,
        "total": len(services),
    }


@router.get("/{service_name}")
async def get_service_status(
    service_name: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status of a specific service.

    Args:
        service_name: Name of the service
        current_user: Authenticated user

    Returns:
        Service status information
    """
    manager = get_docker_manager()
    status = manager.get_service_status(service_name)

    return status


@router.post("/{service_name}/start")
async def start_service(
    service_name: str,
    current_user: User = Depends(get_current_user),
):
    """
    Start a service.

    Args:
        service_name: Name of the service to start
        current_user: Authenticated user

    Returns:
        Operation result
    """
    manager = get_docker_manager()
    result = await manager.start_service(service_name)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/{service_name}/stop")
async def stop_service(
    service_name: str,
    action: ServiceAction = ServiceAction(),
    current_user: User = Depends(get_current_user),
):
    """
    Stop a service.

    Args:
        service_name: Name of the service to stop
        action: Action parameters (timeout)
        current_user: Authenticated user

    Returns:
        Operation result
    """
    manager = get_docker_manager()
    result = await manager.stop_service(service_name, timeout=action.timeout)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str,
    action: ServiceAction = ServiceAction(),
    current_user: User = Depends(get_current_user),
):
    """
    Restart a service.

    Args:
        service_name: Name of the service to restart
        action: Action parameters (timeout)
        current_user: Authenticated user

    Returns:
        Operation result
    """
    manager = get_docker_manager()
    result = await manager.restart_service(service_name, timeout=action.timeout)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/{service_name}/logs")
async def get_service_logs(
    service_name: str,
    tail: int = Query(100, ge=1, le=1000, description="Number of lines to retrieve"),
    current_user: User = Depends(get_current_user),
):
    """
    Get logs from a service.

    Args:
        service_name: Name of the service
        tail: Number of lines from the end of the logs
        current_user: Authenticated user

    Returns:
        Service logs
    """
    manager = get_docker_manager()
    result = manager.get_logs(service_name, tail=tail)

    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])

    return result
