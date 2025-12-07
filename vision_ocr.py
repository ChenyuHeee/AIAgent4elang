import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import httpx


@dataclass
class OCRConfig:
    mode: str = "swift_vision"
    script_path: str = "./scripts/vision_cli.swift"
    service_url: str = "http://localhost:9000/ocr"


class VisionOCR:
    def __init__(self, cfg: OCRConfig) -> None:
        self.cfg = cfg

    async def run(self, image_path: str) -> Dict[str, Any]:
        if self.cfg.mode == "swift_vision":
            return await self._swift_vision(image_path)
        return await self._rapidocr(image_path)

    async def _swift_vision(self, image_path: str) -> Dict[str, Any]:
        Path(image_path).expanduser().resolve()
        cmd = ["swift", self.cfg.script_path, image_path]
        try:
            raw = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            return {"text": "", "error": str(exc)}

    async def _rapidocr(self, image_path: str) -> Dict[str, Any]:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(self.cfg.service_url, json={"image": b64})
            resp.raise_for_status()
            return resp.json()


def load_config(config: Dict[str, Any]) -> OCRConfig:
    cfg = config.get("ocr", {})
    return OCRConfig(
        mode=cfg.get("mode", "swift_vision"),
        script_path=cfg.get("script_path", "./scripts/vision_cli.swift"),
        service_url=cfg.get("service_url", "http://localhost:9000/ocr"),
    )
