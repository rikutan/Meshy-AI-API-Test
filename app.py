import os, json, time
from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    send_from_directory,
)
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
from flask.typing import ResponseReturnValue

# ---- 環境
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
DEMO_MODE = os.getenv("DEMO_MODE", "0").lower() in ("1", "true", "on")
SAMPLE_GLB = "https://modelviewer.dev/shared-assets/models/Astronaut.glb"
SAMPLE_THUMB = "https://modelviewer.dev/shared-assets/thumbnails/Astronaut.webp"

# --- 任意: CORS
try:
    from flask_cors import CORS

    _HAS_CORS = True
except Exception:
    _HAS_CORS = False

# ---- アートスタイル
ALLOWED_ART_STYLES = {"realistic", "sculpture"}
STYLE_FALLBACKS = {
    "cartoon": "realistic",
    "lowpoly": "realistic",
    "anime": "realistic",
    "toon": "realistic",
}


def normalize_art_style(s: str | None) -> str:
    if not s:
        return "realistic"
    s = s.strip().lower()
    return s if s in ALLOWED_ART_STYLES else STYLE_FALLBACKS.get(s, "realistic")


# ---- 外部クライアント
from utils.meshy_client import (
    create_text_to_3d_preview,
    create_text_to_3d_refine,
    get_text_to_3d_task,
    create_rigging_task,
    get_rigging_task,
    create_animation_task,
    get_animation_task,
    download_file,
    MeshyError,
)
from utils.gemini_client import generate_questions_v1, summarize_profile_jp

# 🔥 Firebase
from utils.firebase_storage import register_model_from_url, list_models

# ---- Flask
app = Flask(__name__, static_folder="static", template_folder="templates")
if _HAS_CORS:
    CORS(app, resources={r"/api/*": {"origins": "*"}})

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ---- ログ & キャッシュ
@app.before_request
def _log_req():
    print(f">>> {request.method} {request.path}")


@app.after_request
def nocache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(Exception)
def handle_any_exception(e: Exception) -> ResponseReturnValue:
    status = int(e.code) if isinstance(e, HTTPException) and e.code is not None else 500
    return jsonify({"error": f"{e.__class__.__name__}: {e}"}), status


# ---- ページ
@app.route("/")
def root():
    return render_template("top.html")


@app.route("/quiz")
def quiz_page():
    return render_template("quiz.html")


@app.route("/result")
def result_page():
    return render_template("result.html")


@app.route("/zukan")
def zukan_page():
    return render_template("zukan.html")


# ---- 疎通
@app.get("/api/ping")
def api_ping():
    return jsonify({"ok": True, "pong": True})


# ---- 図鑑 API
@app.route("/api/catalog", methods=["GET"])
def api_catalog_list():
    try:
        models = list_models(limit=50)
        return jsonify({"ok": True, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/catalog/register", methods=["POST"])
def api_catalog_register():
    try:
        data = request.get_json(force=True) or {}
        mesh_url = (data.get("mesh_url") or "").strip()
        if not mesh_url:
            return jsonify({"ok": False, "error": "mesh_url が指定されていません"}), 400
        title_or_meta = data.get("title") or "生成モデル"
        extra = {
            "user": data.get("user") or "anonymous",
            "profile": data.get("profile") or {},
            "ext": "glb",
            "slug": (data.get("title") if isinstance(data.get("title"), str) else None)
            or "model",
            "thumbnail_url": data.get("thumbnail_url") or None,
        }
        saved = register_model_from_url(mesh_url, title_or_meta, extra)
        return jsonify({"ok": True, "model": saved})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---- 診断質問
@app.get("/api/quiz/questions")
def api_quiz_questions():
    try:
        count = int(request.args.get("count", 10))
    except Exception:
        count = 10
    count = max(1, min(10, count))
    return jsonify(generate_questions_v1(desired_count=count))


# ---- スコア定義
TRAITS = [
    {"id": "energy", "left": "内向的", "right": "外交的"},
    {"id": "imagination", "left": "現実志向", "right": "直感的"},
    {"id": "decision", "left": "感情重視", "right": "論理重視"},
    {"id": "order", "left": "柔軟", "right": "計画的"},
]
FIVE_CHOICES_SCORES = [-2, -1, 0, 1, 2]


def scores_to_profile(scores: dict[str, int]) -> dict:
    norm = {k: max(-1.0, min(1.0, v / 20.0)) for k, v in scores.items()}
    vibe = []
    if norm.get("energy", 0) > 0.2:
        vibe.append("cheerful")
    elif norm.get("energy", 0) < -0.2:
        vibe.append("calm")
    if norm.get("decision", 0) > 0.2:
        vibe.append("cool and sharp")
    elif norm.get("decision", 0) < -0.2:
        vibe.append("cute and friendly")
    theme = "fantasy mage" if norm.get("imagination", 0) > 0 else "student uniform"
    details = (
        "tidy and organized outfit"
        if norm.get("order", 0) > 0
        else "playful accessories"
    )
    e = norm.get("energy", 0)
    d = norm.get("decision", 0)
    if e >= 0.3 and d <= 0:
        color = "pastel pink"
    elif e >= 0.3 and d > 0:
        color = "mint green"
    elif e < 0.3 and d > 0:
        color = "navy blue"
    else:
        color = "lavender"
    return {
        "vibe": vibe or ["balanced"],
        "theme": theme,
        "details": details,
        "color": color,
        "norm": norm,
    }


def profile_to_prompt(profile: dict) -> tuple[str, str]:
    """リギングしやすい“人型二足歩行”の指示に最適化"""
    tags = [
        "humanoid bipedal character, humanlike proportions",
        "clear limbs and joints, rig-friendly topology",
        "standing A or T-pose, facing front",
        ", ".join(profile["vibe"]),
        f'{profile["color"]} color scheme',
        profile["theme"],
        profile["details"],
        "anime or stylized, cel-shaded, clean topology",
        "single character, full-body",
    ]
    prompt = ", ".join(tags)
    negative = "super-deformed, chibi, 2.5-heads, big head small body, low quality, low resolution, low poly, deformed hands, extra limbs, photorealistic"
    return prompt, negative


def scores_to_summary_lines(profile: dict) -> list[str]:
    n = profile["norm"]

    def side(t, l, r):
        v = n.get(t, 0)
        if v > 0.3:
            return f"{r}寄り"
        if v < -0.3:
            return f"{l}寄り"
        return "バランス型"

    return [
        f"エネルギー: {side('energy','内向','外向')} / 発想: {side('imagination','現実','直感')}",
        f"判断: {side('decision','感情','論理')} / 進め方: {side('order','柔軟','計画')}",
        f"雰囲気は {', '.join(profile['vibe'])}、テーマは {profile['theme']}、基調色は {profile['color']}。",
    ]


# ---- 内部: Meshy待ち
def _wait_task_succeeded(task_id: str, max_wait_sec: int = 120, interval_sec: int = 2):
    waited = 0
    last = None
    while waited < max_wait_sec:
        last = get_text_to_3d_task(task_id)
        if last.get("status") == "SUCCEEDED":
            return last
        time.sleep(interval_sec)
        waited += interval_sec
    return last


# ---- 診断送信
@app.post("/api/quiz/submit")
def api_quiz_submit():
    data = request.get_json(force=True) or {}
    answers = data.get("answers")

    # --- 通常経路
    if isinstance(answers, list) and answers:
        scores = {t["id"]: 0 for t in TRAITS}
        for a in answers:
            trait_id = str(a.get("trait_id") or "")
            idx = max(0, min(4, int(a.get("choice_index", 2))))
            if trait_id in scores:
                scores[trait_id] += FIVE_CHOICES_SCORES[idx] * 2

        profile = scores_to_profile(scores)
        prompt, negative = profile_to_prompt(profile)
        summary_text = summarize_profile_jp(profile)

        art_style = normalize_art_style(data.get("art_style"))
        should_remesh = bool(data.get("should_remesh", True))
        is_a_t_pose = bool(data.get("is_a_t_pose", True))

        if DEMO_MODE:
            saved = register_model_from_url(
                SAMPLE_GLB,
                title_or_meta="デモモデル",
                extra={
                    "user": "anonymous",
                    "profile": profile,
                    "thumbnail_url": SAMPLE_THUMB,
                },
            )
            return jsonify(
                {
                    "mode": "scores",
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "derived_prompt": prompt,
                    "summary_lines": scores_to_summary_lines(profile),
                    "summary_text": summary_text,
                    "profile": profile,
                    "model_urls": {"glb": SAMPLE_GLB},
                    "saved_model": saved,
                }
            )

        try:
            # Text-to-3D Preview (v2)
            task_id = create_text_to_3d_preview(
                {
                    "prompt": prompt,
                    "negative_prompt": negative,
                    "art_style": art_style,
                    "should_remesh": should_remesh,
                    "is_a_t_pose": is_a_t_pose,
                    # Meshy 6 Preview は create_text_to_3d_preview 側で既定 ai_model=latest
                }
            )

            # ここで成功待ち → 自動登録（任意）
            result = _wait_task_succeeded(task_id, max_wait_sec=120, interval_sec=2)
            if result and result.get("status") == "SUCCEEDED":
                mesh_url = (result.get("model_urls") or {}).get("glb")
                thumb_url = result.get("thumbnail_url")
                if mesh_url:
                    register_model_from_url(
                        mesh_url,
                        title_or_meta=prompt,
                        extra={
                            "user": "anonymous",
                            "profile": profile,
                            "thumbnail_url": thumb_url,
                        },
                    )

            return jsonify(
                {
                    "mode": "scores",
                    "task_id": task_id,
                    "derived_prompt": prompt,
                    "summary_lines": scores_to_summary_lines(profile),
                    "summary_text": summary_text,
                    "profile": profile,
                }
            )
        except MeshyError as e:
            return jsonify({"error": str(e)}), 400

    # --- MBTI互換
    mbti = (data.get("mbti") or "ENFP").upper()
    prompt, negative = profile_to_prompt(
        scores_to_profile(
            {
                "energy": 1 if "E" in mbti else -1,
                "imagination": 1 if "N" in mbti else -1,
                "decision": 1 if "T" in mbti else -1,
                "order": 1 if "J" in mbti else -1,
            }
        )
    )
    summary_text = "あなたはバランスのとれた傾向があります。良い点は前向きさです。留意点は状況に応じて柔軟に。"

    art_style = normalize_art_style(data.get("art_style"))
    should_remesh = bool(data.get("should_remesh", True))
    is_a_t_pose = bool(data.get("is_a_t_pose", True))

    if DEMO_MODE:
        saved = register_model_from_url(
            SAMPLE_GLB,
            title_or_meta="デモモデル",
            extra={"user": "anonymous", "profile": {}, "thumbnail_url": SAMPLE_THUMB},
        )
        return jsonify(
            {
                "task_id": "demo_preview_1",
                "derived_prompt": prompt,
                "mbti": mbti,
                "summary_text": summary_text,
                "saved_model": saved,
            }
        )

    try:
        task_id = create_text_to_3d_preview(
            {
                "prompt": prompt,
                "negative_prompt": negative,
                "art_style": art_style,
                "should_remesh": should_remesh,
                "is_a_t_pose": is_a_t_pose,
            }
        )
        return jsonify(
            {
                "task_id": task_id,
                "derived_prompt": prompt,
                "mbti": mbti,
                "summary_text": summary_text,
            }
        )
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


# ---- 進捗
@app.get("/api/text-to-3d/<task_id>")
def api_get_task(task_id: str):
    if DEMO_MODE and task_id.startswith("demo_"):
        return jsonify(
            {
                "status": "SUCCEEDED",
                "progress": 100,
                "model_urls": {"glb": SAMPLE_GLB},
                "texture_urls": [],
            }
        )
    try:
        return jsonify(get_text_to_3d_task(task_id))
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


# ---- Refine
@app.post("/api/text-to-3d/<preview_task_id>/refine")
def api_refine(preview_task_id: str):
    data = request.get_json(silent=True) or {}
    art_style = normalize_art_style(data.get("art_style"))
    enable_pbr = bool(data.get("enable_pbr", art_style != "sculpture"))
    texture_prompt = (data.get("texture_prompt") or "").strip() or None
    try:
        refine_id = create_text_to_3d_refine(
            {
                "preview_task_id": preview_task_id,
                "enable_pbr": enable_pbr,
                **({"texture_prompt": texture_prompt} if texture_prompt else {}),
            }
        )
        return jsonify({"refine_task_id": refine_id})
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


# ---- Rigging
@app.post("/api/rigging")
def api_rigging_create():
    data = request.get_json(force=True) or {}
    input_task_id = (data.get("input_task_id") or "").strip() or None
    model_url = (data.get("model_url") or "").strip() or None
    try:
        rig_id = create_rigging_task(
            input_task_id=input_task_id,
            model_url=model_url,
            height_meters=float(data.get("height_meters", 1.7)),
        )
        return jsonify({"rig_task_id": rig_id})
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/rigging/<task_id>")
def api_rigging_get(task_id: str):
    try:
        return jsonify(get_rigging_task(task_id))
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


# ---- Animation
@app.post("/api/animations")
def api_animations_create():
    data = request.get_json(force=True) or {}
    rig_task_id = (data.get("rig_task_id") or "").strip()
    action_id = int(data.get("action_id", 0))
    post_process = data.get("post_process") or None
    try:
        ani_id = create_animation_task(
            rig_task_id=rig_task_id, action_id=action_id, post_process=post_process
        )
        return jsonify({"animation_task_id": ani_id})
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/api/animations/<task_id>")
def api_animations_get(task_id: str):
    try:
        return jsonify(get_animation_task(task_id))
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


# ---- ダウンロード中継
@app.post("/api/download")
def api_download():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    filename = (data.get("filename") or "model.glb").strip() or "model.glb"
    dest = os.path.join(DOWNLOAD_DIR, os.path.basename(filename))
    try:
        if not url.startswith(("http://", "https://")):
            return jsonify({"error": "Download failed: invalid url"}), 400
        path = download_file(url, dest)
        return jsonify({"saved": f"/downloads/{os.path.basename(path)}"})
    except MeshyError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/downloads/<path:fname>")
def serve_download(fname: str):
    return send_from_directory(DOWNLOAD_DIR, fname, as_attachment=False)


# ---- 起動
if __name__ == "__main__":
    port_env = os.getenv("PORT", os.getenv("FLASK_RUN_PORT", "5173"))
    try:
        debug_flag = bool(int(os.getenv("FLASK_DEBUG", "0")))
    except ValueError:
        debug_flag = os.getenv("FLASK_DEBUG", "0").lower() in ("true", "1", "yes", "on")
    app.run(host="0.0.0.0", port=int(port_env), debug=debug_flag)
