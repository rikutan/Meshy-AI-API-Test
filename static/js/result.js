// === 設定 ===
const AUTO_SAVE_LOCAL = true;   // /api/download でローカルに中継保存
const REFINE_AUTORUN = true;    // プレビュー成功後に自動で Refine 走らせる

// === util ===
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(ok => setTimeout(ok, ms));

// 図鑑登録で使う「元のGLB URL」を保持（/downloads に置換する前のURL）
let ORIGINAL_GLB_URL = null;

// === Overlay ===
function showOverlay(label) {
    $("loadLabel").textContent = label || "3Dモデルを生成中…";
    $("progressBar").style.width = "0%";
    $("progressText").textContent = "0%";
    $("loadingOverlay").classList.remove("hidden");
}
function updateOverlay(pct, label) {
    if (label) $("loadLabel").textContent = label;
    $("progressBar").style.width = `${pct}%`;
    $("progressText").textContent = `${pct}%`;
}
function hideOverlay() { $("loadingOverlay").classList.add("hidden"); }

// === サマリー表示 ===
function setSummaryText() {
    const text = sessionStorage.getItem("diag.summary_text") || "";
    if (text) {
        $("sumText").textContent = text;
        ["sum1", "sum2", "sum3"].forEach(id => $(id).style.display = "none");
        return;
    }
    const lines = JSON.parse(sessionStorage.getItem("diag.summary") || "[]");
    $("sum1").textContent = lines[0] || "";
    $("sum2").textContent = lines[1] || "";
    $("sum3").textContent = lines[2] || "";
}

// === 図鑑登録 ===
async function registerToCatalog() {
    if (!ORIGINAL_GLB_URL) {
        alert("GLBのURLが見つかりません。生成完了後にお試しください。");
        return;
    }

    const promptTitle =
        (sessionStorage.getItem("diag.title") ||
            sessionStorage.getItem("diag.derived_prompt") || "").slice(0, 48);
    const title = window.prompt("図鑑に表示するタイトル（任意）", promptTitle || "生成モデル");

    const payload = {
        mesh_url: ORIGINAL_GLB_URL, // 元のURLで登録する（/downloads経由ではない）
        title: title || "生成モデル",
        user: window.localStorage.getItem("nickname") || "anonymous",
        profile: safeParse(sessionStorage.getItem("diag.profile")) || {}
    };

    try {
        const res = await fetch("/api/catalog/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const j = await res.json();
        if (j.ok) {
            alert("図鑑に登録しました！");
            if (confirm("図鑑ページを開きますか？")) location.href = "/zukan";
        } else {
            alert("登録に失敗: " + (j.error || "unknown"));
        }
    } catch (e) {
        alert("通信エラー: " + e.message);
    }
}

function safeParse(s) { try { return s ? JSON.parse(s) : null; } catch { return null; } }

// === 3Dモデル表示 ===
async function showModel(glbUrl) {
    ORIGINAL_GLB_URL = glbUrl; // 登録用に保持

    let src = glbUrl;
    if (AUTO_SAVE_LOCAL) {
        try {
            const d = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: glbUrl, filename: "character.glb" })
            }).then(r => r.json());
            if (d.saved) src = d.saved;
        } catch (_) {
            // 中継保存に失敗しても継続
        }
    }

    $("viewer").setAttribute("src", src);
    hideOverlay();
    if ($("miniProgress")) $("miniProgress").style.display = "none";
    $("resultCard")?.scrollIntoView({ behavior: "smooth", block: "center" });

    // 図鑑登録ボタンを解放
    const registerBtn = $("registerBtn");
    if (registerBtn) registerBtn.hidden = false;
}

// === Refine 起動 ===
async function startRefine(previewTaskId) {
    const texturePrompt =
        sessionStorage.getItem("diag.texture_prompt") ||
        sessionStorage.getItem("diag.derived_prompt") || "";
    const artStyle = sessionStorage.getItem("diag.art_style") || "realistic";

    const res = await fetch(`/api/text-to-3d/${encodeURIComponent(previewTaskId)}/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            texture_prompt: texturePrompt,
            art_style: artStyle,
            enable_pbr: (artStyle !== "sculpture"),
        }),
    });
    const j = await res.json();
    if (j.error) throw new Error(j.error);
    return j.refine_task_id;
}

// === ポーリング（Preview task id を保持してRefineへ渡す） ===
async function pollTask(taskId, previewTaskId = null) {
    if (!previewTaskId) previewTaskId = taskId; // 最初のIDをプレビューIDとして固定

    let done = false;
    while (!done) {
        const r = await fetch(`/api/text-to-3d/${encodeURIComponent(taskId)}`);
        const j = await r.json();
        if (j.error) throw new Error(j.error);

        const pct = Math.max(0, Math.min(100, j.progress || 0));
        updateOverlay(pct);
        if ($("miniBar")) $("miniBar").style.width = `${pct}%`;

        if (j.status === "SUCCEEDED") {
            // プレビュー完了時のみ自動Refineするのが安全
            const isPreview = (j.mode === "preview");
            const hasTex = !!(j.texture_urls && j.texture_urls.length > 0);

            if (REFINE_AUTORUN && (isPreview || !hasTex)) {
                updateOverlay(pct, "テクスチャ（色）を生成中…");
                const refineId = await startRefine(previewTaskId); // ★ ここがポイント
                await pollTask(refineId, previewTaskId);           // ★ プレビューIDを引き継ぐ
            } else {
                const glb = j.model_urls && j.model_urls.glb;
                if (!glb) throw new Error("GLB URL not found");
                await showModel(glb);
            }
            done = true;

        } else if (j.status === "FAILED" || j.status === "CANCELLED") {
            throw new Error(j.status);
        } else {
            await sleep(1200);
        }
    }
}

// === init ===
(function init() {
    setSummaryText();

    // 図鑑登録ボタン
    const registerBtn = $("registerBtn");
    if (registerBtn) {
        registerBtn.addEventListener("click", registerToCatalog);
        registerBtn.hidden = true; // 生成完了まで非表示
    }

    const url = new URL(location.href);
    const taskId = url.searchParams.get("task");
    const glb = sessionStorage.getItem("diag.glb");

    if (glb) {
        showModel(glb);
        return;
    }

    if (taskId) {
        showOverlay("メッシュ（形状）を生成中…");
        pollTask(taskId).catch(e => {
            hideOverlay();
            if ($("miniProgress")) $("miniProgress").style.display = "none";
            alert("生成エラー: " + e.message);
        });
    } else {
        if ($("miniProgress")) $("miniProgress").style.display = "none";
    }
})();
