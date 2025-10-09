import os
import requests
from typing import Dict, Any

# ---- 基本設定
MESHY_BASE = "https://api.meshy.ai"


class MeshyError(RuntimeError):
    """Meshy API関連のエラーを表すカスタム例外"""
    pass


# ---- ヘッダー生成
def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('MESHY_API_KEY', '')}",
        "Content-Type": "application/json",
    }


# ---- APIキー確認
def _check_key():
    if not os.getenv("MESHY_API_KEY", "").strip():
        raise MeshyError("Missing MESHY_API_KEY. Put it in .env")


# ---- エラーハンドリング
def _raise_for_error(r: requests.Response, prefix: str):
    if not r.ok:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise MeshyError(f"{prefix}: {r.status_code} {detail}")


# ---- Preview 生成
def create_text_to_3d_preview(payload: Dict[str, Any]) -> str:
    _check_key()
    body = {
        "mode": "preview",
        "prompt": payload["prompt"],
    }

    # 任意パラメータを動的に追加
    for k in [
        "art_style",
        "seed",
        "ai_model",
        "topology",
        "target_polycount",
        "should_remesh",
        "symmetry_mode",
        "is_a_t_pose",
        "moderation",
    ]:
        if k in payload and payload[k] is not None:
            body[k] = payload[k]

    # ✅ URL修正：/openapi/v2 → /v2
    r = requests.post(
        f"{MESHY_BASE}/v2/text-to-3d",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    _raise_for_error(r, "Preview create failed")

    # Meshyのレスポンス形式が変わる可能性もあるため安全に取得
    result = r.json()
    if "result" not in result:
        raise MeshyError(f"Unexpected response: {result}")
    return result["result"]  # task_id


# ---- Refine
def create_text_to_3d_refine(payload: Dict[str, Any]) -> str:
    """
    必須: preview_task_id
    任意: enable_pbr(bool), texture_prompt(str), texture_image_url(str), ai_model(str), moderation(bool)
    """
    _check_key()
    if not payload.get("preview_task_id"):
        raise MeshyError("Refine failed: preview_task_id is empty.")

    body = {
        "mode": "refine",
        "preview_task_id": payload["preview_task_id"],
    }

    for k in [
        "enable_pbr",
        "texture_prompt",
        "texture_image_url",
        "ai_model",
        "moderation",
    ]:
        if k in payload and payload[k] not in (None, ""):
            body[k] = payload[k]

    r = requests.post(
        f"{MESHY_BASE}/v2/text-to-3d",
        headers=_headers(),
        json=body,
        timeout=60,
    )
    _raise_for_error(r, "Refine create failed")

    result = r.json()
    if "result" not in result:
        raise MeshyError(f"Unexpected response: {result}")
    return result["result"]


# ---- タスク取得
def get_text_to_3d_task(task_id: str) -> Dict[str, Any]:
    _check_key()
    if not task_id:
        raise MeshyError("Get task failed: task_id is empty.")

    r = requests.get(
        f"{MESHY_BASE}/v2/text-to-3d/{task_id}",
        headers=_headers(),
        timeout=60,
    )
    _raise_for_error(r, "Get task failed")

    try:
        return r.json()
    except Exception as e:
        raise MeshyError(f"Invalid JSON response: {e}")


# ---- ファイルダウンロード
def download_file(url: str, dest_path: str) -> str:
    if not url:
        raise MeshyError("Download failed: url is empty.")
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return dest_path
