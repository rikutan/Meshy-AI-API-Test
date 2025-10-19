const DEFAULT_ART_STYLE = "realistic";
const DEFAULT_REMESH = true;
const DEFAULT_TPOSE = true;

const $ = id => document.getElementById(id);
let QUESTIONS = [];
let ANSWERS = [];
let idx = 0;

// ======= クリック多重防止ロック =======
const LOCK = { submitting: false };

// ======= overlay =======
function showOverlay(label) {
  $("loadLabel").textContent = label || "送信中…";
  $("progressBar").style.width = "0%";
  $("progressText").textContent = "0%";
  $("loadingOverlay").classList.remove("hidden");
}
function hideOverlay() {
  $("loadingOverlay").classList.add("hidden");
}

// ======= 選択肢ユーティリティ =======
const HIDE_MARKERS_RE = /[\(（\[]\s*(強く\s*左|やや\s*左|中立|やや\s*右|強く\s*右)\s*[\)）\]]/g;
function cleanLabel(s = "") {
  return String(s).replace(HIDE_MARKERS_RE, "").trim();
}

function disableOptions() {
  const btns = document.querySelectorAll("#qOptions .option");
  btns.forEach(b => (b.disabled = true));
  // 念のためクリック判定も切る
  const wrap = $("qOptions");
  if (wrap) wrap.style.pointerEvents = "none";
}

function enableOptions() {
  const btns = document.querySelectorAll("#qOptions .option");
  btns.forEach(b => (b.disabled = false));
  const wrap = $("qOptions");
  if (wrap) wrap.style.pointerEvents = "";
}

function renderQ() {
  const q = QUESTIONS[idx];
  $("qNumber").textContent = `Q.${idx + 1}`;
  $("qTitle").textContent = cleanLabel(q.title || q.text || "(無題)");
  $("qOptions").innerHTML = "";
  (q.options || []).slice(0, 5).forEach((label, i) => {
    const btn = document.createElement("button");
    btn.className = "option";
    btn.textContent = cleanLabel(label);
    btn.onclick = () => choose(i);
    $("qOptions").appendChild(btn);
  });
  $("progressCount").textContent = `${idx + 1} / ${QUESTIONS.length}`;
}

// ======= 回答処理 =======
function choose(choiceIndex) {
  // 既に送信中なら何もさせない（多重クリック対策）
  if (LOCK.submitting) return;

  const q = QUESTIONS[idx];
  const id = q.id || `q${idx + 1}`;
  const trait_id = q.trait_id || "energy";
  ANSWERS.push({ id, trait_id, choice_index: choiceIndex });

  const isLast = (idx + 1 >= QUESTIONS.length);
  if (isLast) {
    // 10問目：ここで即ロック＆ローディング表示
    LOCK.submitting = true;
    disableOptions();
    showOverlay("送信中…結果をまとめています…");
    // 送信開始
    submitAnswers();
  } else {
    idx++;
    renderQ();
  }
}

async function loadQuestions() {
  try {
    const r = await fetch("/api/quiz/questions?count=10");
    const data = await r.json();
    QUESTIONS = (data.questions || []).slice(0, 10);
  } catch (_) {
    QUESTIONS = [{
      id: "q1", trait_id: "energy",
      title: "初対面の多い場に行くときは？",
      options: ["できれば避けたい", "少し億劫", "どちらともいえない", "少し楽しみ", "とても楽しみ"]
    }];
  }
  idx = 0; ANSWERS = []; LOCK.submitting = false;
  renderQ();
}

async function submitAnswers() {
  try {
    // 念のため二重ガード（直接呼ばれた時にも対策）
    if (LOCK.submitting !== true) {
      LOCK.submitting = true;
      disableOptions();
      showOverlay("送信中…");
    }

    const res = await fetch("/api/quiz/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        answers: ANSWERS,
        art_style: DEFAULT_ART_STYLE,
        should_remesh: DEFAULT_REMESH,
        is_a_t_pose: DEFAULT_TPOSE,
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    // 結果を保存（/result で使用）
    sessionStorage.setItem("diag.summary", JSON.stringify(data.summary_lines || []));
    if (data.summary_text) sessionStorage.setItem("diag.summary_text", data.summary_text);
    if (data.derived_prompt) sessionStorage.setItem("diag.derived_prompt", data.derived_prompt);
    sessionStorage.setItem("diag.art_style", (DEFAULT_ART_STYLE || "realistic"));

    // ここから結果ページへ遷移（ローディングのまま移動）
    if (data.model_urls && data.model_urls.glb) {
      sessionStorage.setItem("diag.glb", data.model_urls.glb);
      location.href = "/result";
      return;
    }
    const q = new URLSearchParams();
    if (data.task_id) q.set("task", data.task_id);
    location.href = `/result${q.toString() ? "?" + q.toString() : ""}`;
  } catch (e) {
    // 失敗したらロック解除して最初からやり直せるように
    hideOverlay();
    alert("送信エラー: " + e.message);
    idx = 0; ANSWERS = [];
    LOCK.submitting = false;
    enableOptions();
    renderQ();
  }
}

loadQuestions();
