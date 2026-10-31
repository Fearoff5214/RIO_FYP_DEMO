from __future__ import annotations

from pathlib import Path

from app.core.config import get_config


def resolve_capture_path(uri: str) -> Path | None:
    """Resolve a capture only from configured image-storage directories."""
    config = get_config()
    project_root = config.project_root.resolve()
    camera_folder = Path(config.get("camera", "folder_path", default="samples"))
    allowed_roots = [
        project_root / "tmp" / "part_verification",
        camera_folder if camera_folder.is_absolute() else project_root / camera_folder,
    ]

    image_path = Path(uri).resolve()
    for root in allowed_roots:
        try:
            image_path.relative_to(root.resolve())
        except ValueError:
            continue
        return image_path if image_path.is_file() else None

    return None
