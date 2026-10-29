"""Camera adapter factory."""
from __future__ import annotations

from app.core.config import get_config


def get_camera():
    """Return the camera adapter configured by NOVALISEO_MODE / config."""
    cfg = get_config()
    adapter_name = cfg.get("camera", "adapter") or ("mock" if cfg.is_mock else "folder")

    if adapter_name == "mock":
        from app.cv.camera.mock import MockCamera
        return MockCamera()
    elif adapter_name == "folder":
        from app.cv.camera.folder import FolderCamera
        folder = cfg.get("camera", "folder_path") or "samples/"
        return FolderCamera(folder)
    elif adapter_name == "upload":
        from app.cv.camera.upload import UploadCamera
        return UploadCamera()
    elif adapter_name == "genicam":
        from app.cv.camera.genicam import GenICamCamera
        return GenICamCamera()
    else:
        from app.cv.camera.mock import MockCamera
        return MockCamera()
