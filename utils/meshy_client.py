import os
import requests
from typing import Any, Dict, Optional

API_BASE = "https://api.meshy.ai"
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "").strip()
HEADERS_JSON = {
    "Authorization": f"Bearer {MESHY_API_KEY}",
    "Content-Type": "application/json",
}

class MeshyError(Exception):
    pass

def _raise_for_api_error(resp: requests.Response):
    if resp.status_code >= 400:
        try:
            j = resp.json()
        except Exception:
            j = {"message": resp.text}
        raise MeshyError(f"{resp.status_code} {j}")

# ---------- Text-to-3D (v2)
def create_text_to_3d_preview(payload: Dict[str, Any]) -> str:
    """Returns preview task_id"""
    body = {
        "mode": "preview",
        # Meshy 6 Preview + リギング前提の生成に寄せた既定値
        "ai_model": "latest",           # Meshy 6 Preview
        "is_a_t_pose": True,            # A/Tポーズで生成
        "topology": "quad",
        "symmetry_mode": "on",
        "should_remesh": True,
    }
    body.update(payload or {})
    resp = requests.post(f"{API_BASE}/openapi/v2/text-to-3d", json=body, headers=HEADERS_JSON, timeout=60)
    _raise_for_api_error(resp)
    return resp.json().get("result")

def create_text_to_3d_refine(payload: Dict[str, Any]) -> str:
    """payload must include preview_task_id; returns refine task_id"""
    body = {
        "mode": "refine",
        "enable_pbr": True,
    }
    body.update(payload or {})
    resp = requests.post(f"{API_BASE}/openapi/v2/text-to-3d", json=body, headers=HEADERS_JSON, timeout=60)
    _raise_for_api_error(resp)
    return resp.json().get("result")

def get_text_to_3d_task(task_id: str) -> Dict[str, Any]:
    resp = requests.get(f"{API_BASE}/openapi/v2/text-to-3d/{task_id}", headers={"Authorization": f"Bearer {MESHY_API_KEY}"}, timeout=60)
    _raise_for_api_error(resp)
    return resp.json()

# ---------- Rigging (v1)
def create_rigging_task(*, input_task_id: Optional[str] = None, model_url: Optional[str] = None,
                        height_meters: float = 1.7, texture_image_url: Optional[str] = None) -> str:
    if not input_task_id and not model_url:
        raise MeshyError("Either input_task_id or model_url is required for rigging.")
    body: Dict[str, Any] = {
        "height_meters": float(height_meters),
    }
    if input_task_id:
        body["input_task_id"] = input_task_id
    if model_url:
        body["model_url"] = model_url
    if texture_image_url:
        body["texture_image_url"] = texture_image_url

    resp = requests.post(f"{API_BASE}/openapi/v1/rigging", json=body, headers=HEADERS_JSON, timeout=60)
    _raise_for_api_error(resp)
    return resp.json().get("result")

def get_rigging_task(task_id: str) -> Dict[str, Any]:
    resp = requests.get(f"{API_BASE}/openapi/v1/rigging/{task_id}", headers={"Authorization": f"Bearer {MESHY_API_KEY}"}, timeout=60)
    _raise_for_api_error(resp)
    return resp.json()

# ---------- Animation (v1)
def create_animation_task(*, rig_task_id: str, action_id: int, post_process: Optional[Dict[str, Any]] = None) -> str:
    if not rig_task_id:
        raise MeshyError("rig_task_id is required.")
    body: Dict[str, Any] = {
        "rig_task_id": rig_task_id,
        "action_id": int(action_id),
    }
    if post_process:
        body["post_process"] = post_process

    resp = requests.post(f"{API_BASE}/openapi/v1/animations", json=body, headers=HEADERS_JSON, timeout=60)
    _raise_for_api_error(resp)
    return resp.json().get("result")

def get_animation_task(task_id: str) -> Dict[str, Any]:
    resp = requests.get(f"{API_BASE}/openapi/v1/animations/{task_id}", headers={"Authorization": f"Bearer {MESHY_API_KEY}"}, timeout=60)
    _raise_for_api_error(resp)
    return resp.json()

# ---------- Util
def download_file(url: str, dest_path: str) -> str:
    r = requests.get(url, stream=True, timeout=120)
    _raise_for_api_error(r)
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return dest_path
