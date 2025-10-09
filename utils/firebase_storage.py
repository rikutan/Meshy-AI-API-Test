import requests
from datetime import datetime, timezone
from typing import Any, Dict, Union
from firebase_admin import firestore, storage
from firebase_init import init_firebase

db, bucket = init_firebase()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_meta(title_or_meta: Union[str, Dict[str, Any], None], extra: Dict[str, Any]) -> Dict[str, Any]:
    meta = {}
    if isinstance(title_or_meta, str):
        meta["title"] = title_or_meta
    elif isinstance(title_or_meta, dict):
        t = title_or_meta.get("title") if isinstance(title_or_meta.get("title"), str) else None
        meta["title"] = t or title_or_meta.get("slug") or "生成モデル"
        meta.setdefault("user", title_or_meta.get("user"))
        meta.setdefault("profile", title_or_meta.get("profile"))
        meta.setdefault("ext", title_or_meta.get("ext"))
        meta.setdefault("slug", title_or_meta.get("slug"))
    else:
        meta["title"] = "生成モデル"

    meta["user"] = extra.get("user") or meta.get("user") or "anonymous"
    meta["profile"] = extra.get("profile") or meta.get("profile") or {}
    meta["ext"] = extra.get("ext") or meta.get("ext") or "glb"
    meta["slug"] = extra.get("slug") or meta.get("slug") or "model"
    return meta


def register_model_from_url(
    mesh_url: str,
    title_or_meta: Union[str, Dict[str, Any], None] = None,
    extra: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    mesh_urlからGLBを取得→Storageへ保存→Firestoreへ登録。
    thumbnail_url が extra に含まれていたら Firestore にも保存する。
    """
    extra = extra or {}
    meta = _coerce_meta(title_or_meta, extra)

    # GLBを取得
    resp = requests.get(mesh_url)
    resp.raise_for_status()

    filename = f"model_{int(datetime.now().timestamp())}.glb"
    blob_path = f"models/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(resp.content, content_type="model/gltf-binary")
    public_url = blob.public_url

    # Firestore登録
    doc_ref = db.collection("models").document()
    doc_ref.set({
        "title": meta["title"],
        "public_url": public_url,
        "thumbnail_url": extra.get("thumbnail_url"),  # ★追加
        "path": blob_path,
        "user": meta["user"],
        "profile": meta["profile"],
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    return {
        "id": doc_ref.id,
        "title": meta["title"],
        "public_url": public_url,
        "thumbnail_url": extra.get("thumbnail_url"),
        "path": blob_path,
        "user": meta["user"],
        "profile": meta["profile"],
        "created_at": _now_iso(),
    }


def list_models(limit: int = 20) -> list:
    """Firestoreから新しい順で取得。"""
    q = db.collection("models").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
    docs = q.stream()
    items = []
    for d in docs:
        obj = d.to_dict() or {}
        created = obj.get("created_at")
        if hasattr(created, "isoformat"):
            created = created.isoformat()
        elif created is None:
            created = ""
        items.append({
            "id": d.id,
            "title": obj.get("title") or "生成モデル",
            "public_url": obj.get("public_url"),
            "thumbnail_url": obj.get("thumbnail_url"),  # ★追加
            "path": obj.get("path"),
            "user": obj.get("user") or "anonymous",
            "profile": obj.get("profile") or {},
            "created_at": created,
        })
    return items
