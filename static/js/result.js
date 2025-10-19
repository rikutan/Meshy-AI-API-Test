// === 設定 ===
const AUTO_SAVE_LOCAL = true;   // /api/download でローカルに中継保存
const REFINE_AUTORUN = true;    // プレビュー成功後に自動で Refine 走らせる

// === util ===
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(ok => setTimeout(ok, ms));
const safeParse = s => { try { return s ? JSON.parse(s) : null; } catch { return null; } };

// 図鑑登録で使う「元のGLB URL」を保持（/downloads に置換する前のURL）
let ORIGINAL_GLB_URL = null;

// Text-to-3D の各 task_id
let PREVIEW_TASK_ID = null;
let REFINE_TASK_ID = null;

// ★ リギング作成レスで返るIDを厳密に保持（これを animations に渡す）
let RIG_TASK_ID = sessionStorage.getItem("rig.task_id") || null;

// === Overlay ===
function showOverlay(label) {
    $("loadLabel").textContent = label || "3Dモデルを生成中…";
    $("progressBar").style.width = "0%";
    $("progressText").textContent = "0%";
    $("loadingOverlay").classList.remove("hidden");
}
function updateOverlay(pct, label) {
    if (label) $("loadLabel").textContent = label;
    const p = Math.max(0, Math.min(100, Math.floor(pct || 0)));
    $("progressBar").style.width = `${p}%`;
    $("progressText").textContent = `${p}%`;
    if ($("miniBar")) $("miniBar").style.width = `${p}%`;
    if ($("miniPct")) $("miniPct").textContent = `${p}%`;
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
        mesh_url: ORIGINAL_GLB_URL,
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

// === 3Dモデル表示 ===
async function showModel(glbUrl) {
    ORIGINAL_GLB_URL = glbUrl; // 登録用に保持
    const viewer = $("viewer");

    // 同じURLだと <model-viewer> がリロードしないことがある → 一意ファイル名で保存
    let src = glbUrl;
    if (AUTO_SAVE_LOCAL) {
        const stamp = Date.now();
        const saveName = `character_${stamp}.glb`;
        try {
            const d = await fetch("/api/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: glbUrl, filename: saveName })
            }).then(r => r.json());
            if (d.saved) {
                // キャッシュ回避用のダミークエリも付与
                src = `${d.saved}?v=${stamp}`;
            }
        } catch (_) { /* 中継保存に失敗しても継続 */ }
    }

    // 先に空にしてから再セットすると確実に再読み込みされる
    try { viewer.pause && viewer.pause(); } catch { }
    viewer.removeAttribute("src");
    await sleep(30);

    // ロード完了後に最初のクリップを選んで再生
    const onLoad = () => {
        try {
            const anims = viewer.availableAnimations || [];
            if (anims.length > 0) {
                viewer.animationName = anims[0]; // 明示指定
                viewer.currentTime = 0;
                viewer.play && viewer.play();
                const s = $("animStatus");
                if (s) s.textContent = `再生中: ${viewer.animationName}（クリップ数: ${anims.length}）`;
            } else {
                const s = $("animStatus");
                if (s) s.textContent = "アニメーションクリップが見つかりません（静止モデルとして表示中）";
            }
        } catch (e) {
            const s = $("animStatus");
            if (s) s.textContent = "再生エラー: " + e.message;
        }
    };
    viewer.addEventListener("load", onLoad, { once: true });

    viewer.setAttribute("src", src);

    hideOverlay();
    if ($("miniProgress")) $("miniProgress").style.display = "none";
    $("resultCard")?.scrollIntoView({ behavior: "smooth", block: "center" });

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

// === ポーリング（Text-to-3D） ===
async function pollTask(taskId, mode = "preview", previewTaskId = null) {
    if (mode === "preview") PREVIEW_TASK_ID = taskId;
    if (!previewTaskId) previewTaskId = PREVIEW_TASK_ID;

    let done = false;
    while (!done) {
        const r = await fetch(`/api/text-to-3d/${encodeURIComponent(taskId)}`);
        const j = await r.json();
        if (j.error) throw new Error(j.error);

        const pct = Math.max(0, Math.min(100, j.progress || 0));
        updateOverlay(pct);

        if (j.status === "SUCCEEDED") {
            if (mode === "preview") {
                if (REFINE_AUTORUN) {
                    updateOverlay(pct, "テクスチャ（色）を生成中…");
                    const refineId = await startRefine(previewTaskId);
                    REFINE_TASK_ID = refineId;
                    await pollTask(refineId, "refine", previewTaskId);
                } else {
                    const glb = j.model_urls && j.model_urls.glb;
                    if (!glb) throw new Error("GLB URL not found");
                    await showModel(glb);
                }
            } else {
                REFINE_TASK_ID = taskId;
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

// === Rigging/Animation ===
async function pollRigging(rigId) {
    while (true) {
        const j = await fetch(`/api/rigging/${encodeURIComponent(rigId)}`).then(r => r.json());
        if (j.error) throw new Error(j.error);
        const pct = Math.max(0, Math.min(100, j.progress || 0));
        updateOverlay(pct, "自動リギング中…");
        if (j.status === "SUCCEEDED") return j;
        if (j.status === "FAILED" || j.status === "CANCELLED") throw new Error(j.status);
        await sleep(1200);
    }
}

async function pollAnimation(animId) {
    while (true) {
        const j = await fetch(`/api/animations/${encodeURIComponent(animId)}`).then(r => r.json());
        if (j.error) throw new Error(j.error);
        const pct = Math.max(0, Math.min(100, j.progress || 0));
        updateOverlay(pct, "アニメーション適用中…");
        if (j.status === "SUCCEEDED") return j;
        if (j.status === "FAILED" || j.status === "CANCELLED") throw new Error(j.status);
        await sleep(1200);
    }
}

async function runAnimationFlow(actionId) {
    if (!REFINE_TASK_ID) {
        alert("先にテクスチャ生成（Refine）が必要です。少し待ってからお試しください。");
        return;
    }
    const status = $("animStatus");
    showOverlay("自動リギング中…");

    // 1) Rigging を作成 → 返ってきた result(ID) を RIG_TASK_ID に保存（これを後で必ず渡す）
    const rigRes = await fetch("/api/rigging", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input_task_id: REFINE_TASK_ID, height_meters: 1.7 }),
    }).then(r => r.json());
    if (rigRes.error) throw new Error("Rigging create failed: " + rigRes.error);

    RIG_TASK_ID = rigRes.rig_task_id; // ★ 公式の「作成レスのID」を保持
    sessionStorage.setItem("rig.task_id", RIG_TASK_ID);
    if (status) status.textContent = `リギング開始… (id: ${RIG_TASK_ID})`;

    const rigDone = await pollRigging(RIG_TASK_ID);
    if (status) status.textContent = `アニメーションを生成しています… (rig: ${RIG_TASK_ID})`;

    // 2) Animation 作成時は RIG_TASK_ID を厳密に使用
    const aniRes = await fetch("/api/animations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rig_task_id: RIG_TASK_ID, action_id: Number(actionId) }),
    }).then(r => r.json());
    if (aniRes.error) throw new Error("Animation create failed: " + aniRes.error);

    const aniDone = await pollAnimation(aniRes.animation_task_id);

    const glb = aniDone.result && (aniDone.result.animation_glb_url || aniDone.result.glb_url);
    if (!glb) throw new Error("Animation GLB URL not found");
    if (status) status.textContent = "アニメーションを適用しました（再生を開始します）";
    await showModel(glb);
}

// === init ===
(function init() {
    setSummaryText();

    const registerBtn = $("registerBtn");
    if (registerBtn) {
        registerBtn.addEventListener("click", registerToCatalog);
        registerBtn.hidden = true;
    }

    const animateBtn = $("animateBtn");
    if (animateBtn) {
        animateBtn.addEventListener("click", async () => {
            const actionId = $("animSelect").value;
            try {
                await runAnimationFlow(actionId);
            } catch (e) {
                hideOverlay();
                const s = $("animStatus");
                if (s) s.textContent = "アニメーション生成エラー: " + e.message;
                else alert("アニメーション生成エラー: " + e.message);
            }
        });
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
        pollTask(taskId, "preview").catch(e => {
            hideOverlay();
            if ($("miniProgress")) $("miniProgress").style.display = "none";
            alert("生成エラー: " + e.message);
        });
    } else {
        if ($("miniProgress")) $("miniProgress").style.display = "none";
    }
})();
