import os
import re
import json
from typing import Dict, Any, List

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

_HIDE_RE = re.compile(
    r"[\(\（\[]\s*(?:強く\s*左|やや\s*左|中立|やや\s*右|強く\s*右)\s*[\)\）\]]"
)


def _strip_markers(text: str) -> str:
    return _HIDE_RE.sub("", (text or "")).strip()


PROMPT_SYSTEM = """あなたは日本語でパーソナリティ診断の質問を作るアシスタントです。
出力は必ず JSON のみ。マークダウンや解説は不要。
各質問は次のいずれか1つの trait_id を測定します:
- energy (内向↔外向)
- imagination (現実↔直感)
- decision (感情↔論理)
- order (柔軟↔計画)

各質問は:
- "title": ユーザーに表示する質問文（短く自然な日本語）
- "trait_id": 上のいずれか1つ
- "options": 5つの選択肢テキスト（中立を含む5段階）
  ※ 重要: テキスト中に「強く左／やや左／中立／やや右／強く右」などのラベル語や括弧書きを入れないこと。
"""

PROMPT_USER_TEMPLATE = """次の形式で **ちょうど {count} 問** 生成してください。JSONのみ:
{{
  "version": "v1",
  "questions": [
    {{
      "id": "q1",
      "title": "・・・",
      "trait_id": "energy",
      "options": ["自然文1","自然文2","自然文3","自然文4","自然文5"]
    }}
  ]
}}
"""

LIKERT5 = [
    "全くそう思わない",
    "どちらかといえばそう思わない",
    "どちらとも言えない",
    "どちらかといえばそう思う",
    "そう思う",
]

TRAIT_ORDER = ["energy", "imagination", "decision", "order"]


def generate_questions_v1(desired_count: int = 10) -> Dict[str, Any]:
    """Geminiで質問を作成（失敗時はフォールバック）。"""
    count = max(1, min(10, int(desired_count or 10)))

    if not GEMINI_API_KEY:
        return {"version": "v1", "questions": _fallback_pool()[:count]}

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=PROMPT_SYSTEM,
            generation_config={"response_mime_type": "application/json"},
        )
        resp = model.generate_content(PROMPT_USER_TEMPLATE.format(count=count))
        data = json.loads(resp.text)
        qs: List[Dict[str, Any]] = list(data.get("questions", []))
    except Exception:
        qs = []

    qs = _normalize_qs(qs)
    if len(qs) < count:
        qs = _topup_to_count(qs, count)
    return {"version": "v1", "questions": qs[:count]}


def _normalize_qs(qs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, q in enumerate(qs, 1):
        title = _strip_markers(q.get("title") or "")
        trait = (q.get("trait_id") or "").strip()
        if trait not in TRAIT_ORDER:
            continue
        opts = [_strip_markers(o) for o in list(q.get("options") or [])[:5]]
        while len(opts) < 5:
            opts.append("どちらとも言えない")
        out.append(
            {
                "id": q.get("id") or f"q{i}",
                "title": title or f"質問 {i}",
                "trait_id": trait,
                "options": opts,
            }
        )
    return out


def _topup_to_count(qs: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    used_titles = {q["title"] for q in qs}
    for cand in _fallback_pool():
        if len(qs) >= count:
            break
        if cand["title"] in used_titles:
            continue
        qs.append(cand)
        used_titles.add(cand["title"])

    i = 1
    while len(qs) < count:
        trait = TRAIT_ORDER[(len(qs) + i) % 4]
        title = _synthetic_title(trait, i)
        if title in used_titles:
            i += 1
            continue
        qs.append(
            {
                "id": f"g{len(qs)+1}",
                "title": title,
                "trait_id": trait,
                "options": LIKERT5[:],
            }
        )
        used_titles.add(title)
        i += 1
    return qs


def _synthetic_title(trait: str, i: int) -> str:
    if trait == "energy":
        return "大人数の集まりに参加するとき、気持ちはどうですか？"
    if trait == "imagination":
        return "新しいことを始めるとき、発想はどちらに寄りますか？"
    if trait == "decision":
        return "物事を決めるとき、何を優先しますか？"
    if trait == "order":
        return "予定やタスクの進め方はどちらに近いですか？"
    return f"質問 {i}"


def _fallback_pool() -> List[Dict[str, Any]]:
    F: List[Dict[str, Any]] = []

    def add(title, trait):
        F.append(
            {
                "id": f"q{len(F)+1}",
                "title": title,
                "trait_id": trait,
                "options": LIKERT5[:],
            }
        )

    # energy
    add("初対面が多いイベントに誘われたら、どう感じますか？", "energy")
    add("雑談が続く集まりに参加するのは好きですか？", "energy")
    add("休み時間や休憩中は、人と話すほうですか？", "energy")

    # imagination
    add(
        "新しいアイデアを考えるとき、現実性より発想の面白さを優先しますか？",
        "imagination",
    )
    add("企画のブレストでは、飛躍した案も歓迎しますか？", "imagination")
    add("説明書よりも、直感的に触って覚えるほうですか？", "imagination")

    # decision
    add("人の相談に乗るとき、気持ちより解決策を重視しますか？", "decision")
    add("判断に迷ったら、データや客観性を優先しますか？", "decision")
    add("議論では、筋道が通っていることを最重視しますか？", "decision")

    # order
    add("旅行の計画は、綿密に立てるほうですか？", "order")
    add("締め切りのあるタスク、早めに終わらせるほうですか？", "order")
    add("予定変更より、事前の計画どおり進めるほうが安心ですか？", "order")

    return F


def summarize_profile_jp(profile: Dict[str, Any]) -> str:
    """
    scores_to_profile() が返す profile(dict) から、日本語の1段落（2〜3文）を生成。
    Geminiキーが無い/失敗時は自然なフォールバック文を返す。
    """
    try:
        if not GEMINI_API_KEY:
            return _fallback_summary(profile)

        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)

        system = (
            "あなたは日本語で短い診断結果を作るアシスタントです。"
            "出力はテキストのみ（日本語のみ、英単語は使わない）。"
            "同じ語の過剰な繰り返しや箇条書き・羅列は避け、自然な文にする。"
            "2～3文で、以下の構造を守ってください："
            "1文目:「あなたは、◯◯な傾向があります。」（強く出ている性質だけ1～2個に要約）"
            "2文目:「とてもいい点は、◯◯です。」"
            "3文目:「しかし、気を付けるべきポイントは、◯◯です。」（必要なら2文目と連結可）"
        )

        user = {
            "instruction": "次のプロファイルから文章を生成してください。",
            "profile": profile,
        }

        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=system,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 220,
                "response_mime_type": "text/plain",
            },
        )
        resp = model.generate_content(json.dumps(user, ensure_ascii=False))
        text = (resp.text or "").strip()
        if not text:
            return _fallback_summary(profile)
        if not text.endswith(("。", "！", "!", "？", "?")):
            text += "。"
        return text
    except Exception:
        return _fallback_summary(profile)



_JA_VIBE = {
    "cheerful": "明るく社交的",
    "calm": "落ち着いて思慮深い",
    "cool and sharp": "論理的でキレがある",
    "cute and friendly": "親しみやすく思いやりがある",
    "balanced": "バランスの取れた",
}
_JA_THEME = {
    "student uniform": "落ち着いた学生風の雰囲気",
    "fantasy mage": "自由で創造的な雰囲気",
}
_JA_COLOR = {
    "pastel pink": "パステルピンク",
    "mint green": "ミントグリーン",
    "navy blue": "ネイビーブルー",
    "lavender": "ラベンダー",
}


def _fallback_summary(profile: Dict[str, Any]) -> str:
    n = profile.get("norm", {})

    def score(v):
        try:
            return float(v or 0.0)
        except Exception:
            return 0.0

    # 形容（やや○○ / ○○）を返す。閾値: 強=0.45, 弱=0.20
    def adj(v, left, right):
        v = score(v)
        if v >= 0.45:
            return right
        if 0.20 <= v < 0.45:
            return f"やや{right}"
        if v <= -0.45:
            return left
        if -0.45 < v <= -0.20:
            return f"やや{left}"
        return ""

    axes = [
        ("energy", "内向的", "外向的"),
        ("imagination", "現実的", "直感的"),
        ("decision", "感情的", "論理的"),
        ("order", "柔軟", "計画的"),
    ]
    pairs = []
    for key, left, right in axes:
        a = adj(n.get(key), left, right)
        if a:
            pairs.append((abs(score(n.get(key))), a))
    pairs.sort(key=lambda x: x[0], reverse=True)
    descs = [a for _, a in pairs[:2]]

    vibe_jp = "、".join(_JA_VIBE.get(v, v) for v in profile.get("vibe", []))
    theme = _JA_THEME.get(profile.get("theme"), profile.get("theme"))
    color = _JA_COLOR.get(profile.get("color"), profile.get("color"))

    strengths, cautions = [], []

    def add(cond, good, care):
        if cond:
            strengths.append(good)
            cautions.append(care)

    vE = score(n.get("energy"))
    vI = score(n.get("imagination"))
    vD = score(n.get("decision"))
    vO = score(n.get("order"))
    add(vE > 0.2, "人を巻き込んで行動できる", "一人の時間を軽視しすぎないこと")
    add(vE < -0.2, "集中力が高く深く考えられる", "考えを言語化して伝える意識を持つこと")
    add(vI > 0.2, "発想力と新しい切り口", "実現性や詰めの甘さに注意")
    add(vI < -0.2, "具体化と実行の強さ", "発想の幅をときどき広げる余白を作ること")
    add(vD > 0.2, "客観的な判断と説明の明快さ", "相手の感情面に配慮を忘れないこと")
    add(vD < -0.2, "共感力と関係調整のうまさ", "迷いすぎず結論まで進めること")
    add(vO > 0.2, "段取りと再現性の高さ", "予定変更に柔軟さを残すこと")
    add(vO < -0.2, "臨機応変で変化に強い", "締め切りや優先順位を明確にすること")

    if descs:
        s1 = f"あなたは、{'で'.join(descs)}な傾向があります。"
    else:
        s1 = "あなたは、各面でバランスが取れています。"
    if vibe_jp:
        if s1.endswith("。"):
            s1 = s1[:-1]
        s1 += f"。雰囲気は{vibe_jp}です。"

    good_core = "と".join((strengths[:2] or ["状況に応じて柔軟に動けること"]))
    s2 = f"とてもいい点は、{good_core}です。"

    care_core = "、".join((cautions[:2] or ["得意な型に寄りすぎないこと"]))
    tone = []
    if theme:
        tone.append(f"全体のトーンは{theme}")
    if color:
        tone.append(f"基調色は{color}")
    tail = "。".join(tone) + "。" if tone else "。"
    s3 = f"しかし、気を付けるべきポイントは、{care_core}です{tail}"

    return (s1 + " " + s2 + " " + s3).strip()
