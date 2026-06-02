"""Publisher — exports the run for manual upload, or posts via the TikTok API.

MVP default (``publish.mode: export``): everything is already written to the run
folder; this step just confirms the deliverables and prints next steps.

Optional (``publish.mode: tiktok_api``): upload as a draft via the TikTok Content
Posting API. Requires ``TIKTOK_ACCESS_TOKEN`` with the right scope. We default to
the privacy level in config (``SELF_ONLY``) so nothing goes public by accident.
See https://developers.tiktok.com/doc/content-posting-api-get-started
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import Config
from ..utils import get_logger

log = get_logger("publisher")


def publish(run_dir: str, cfg: Config) -> dict:
    mode = str(cfg.get("publish.mode", "export")).lower()
    run = Path(run_dir)
    video = run / "final_video.mp4"
    caption = (run / "caption.txt").read_text(encoding="utf-8") if (run / "caption.txt").exists() else ""

    if mode == "tiktok_api":
        token = cfg.tiktok_token
        if not token:
            log.warning("publish.mode=tiktok_api but TIKTOK_ACCESS_TOKEN is unset — exporting instead")
        else:
            try:
                return _post_to_tiktok(video, caption, token, cfg)
            except Exception as e:
                log.error("TikTok upload failed (%s) — file is saved for manual upload", e)

    log.info("export ready: %s", video)
    return {"mode": "export", "video": str(video), "uploaded": False,
            "note": "Upload manually with the caption in caption.txt"}


def _post_to_tiktok(video: Path, caption: str, token: str, cfg: Config) -> dict:
    """Direct-post a local video file via the Content Posting API (FILE_UPLOAD)."""
    import requests

    privacy = cfg.get("publish.tiktok_privacy", "SELF_ONLY")
    size = video.stat().st_size
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    init = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {"title": caption[:2200], "privacy_level": privacy},
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        },
        timeout=60,
    )
    init.raise_for_status()
    data = init.json()["data"]
    upload_url = data["upload_url"]
    publish_id = data["publish_id"]

    with open(video, "rb") as f:
        requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            },
            data=f.read(),
            timeout=300,
        ).raise_for_status()

    log.info("TikTok upload accepted (publish_id=%s, privacy=%s)", publish_id, privacy)
    return {"mode": "tiktok_api", "uploaded": True, "publish_id": publish_id, "privacy": privacy}
