from pathlib import Path

from shared.config import BASE_DIR

ASSETS_DIR = BASE_DIR / "assets"

PHOTOS = {
    "start": ASSETS_DIR / "start.jpg",
    "user_verified": ASSETS_DIR / "user_verified.jpg",
    "info": ASSETS_DIR / "info.jpg",
    "report": ASSETS_DIR / "report.jpg",
    "admins": ASSETS_DIR / "admins.jpg",
    "garants": ASSETS_DIR / "garants.jpg",
    "garant_elite": ASSETS_DIR / "garant_elite.jpg",
    "garant_top": ASSETS_DIR / "garant_top.jpg",
    "garant_regular": ASSETS_DIR / "garant_regular.jpg",
    "user_scammer": ASSETS_DIR / "user_scammer.jpg",
    "user_suspicious": ASSETS_DIR / "user_suspicious.jpg",
}

VIDEOS = {
    "garant_top_extra": ASSETS_DIR / "garant_top_extra.mov",
}

COMMAND_PHOTOS = {
    "start": "start",
    "info": "info",
    "admins": "admins",
    "garants": "garants",
    "help": "info",
}


def get_photo(name: str) -> Path | None:
    path = PHOTOS.get(name)
    if path and path.is_file():
        return path
    return None


def get_video(name: str) -> Path | None:
    path = VIDEOS.get(name)
    if path and path.is_file():
        return path
    return None


def photo_for_command(cmd: str) -> Path | None:
    key = COMMAND_PHOTOS.get(cmd.lstrip("/").lower())
    return get_photo(key) if key else None