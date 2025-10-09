document.addEventListener("DOMContentLoaded", async () => {
    const grid = document.getElementById("zukan-list");

    const renderCard = (item) => {
        const card = document.createElement("div");
        card.className = "card";

        const title =
            (typeof item.title === "object" ? item.title.title : item.title) || "無題モデル";
        const user = item.user || "anonymous";

        if (item.thumbnail_url) {
            // 静的サムネイル（軽量）
            const img = document.createElement("img");
            img.src = item.thumbnail_url;
            img.alt = title;
            img.className = "thumb";
            card.appendChild(img);
        } else {
            // fallback: モデルを直接表示
            const mv = document.createElement("model-viewer");
            mv.src = item.public_url;
            mv.alt = title;
            mv.cameraControls = true;
            mv.autoRotate = true;
            mv.style.width = "240px";
            mv.style.height = "240px";
            card.appendChild(mv);
        }

        const h3 = document.createElement("h3");
        h3.textContent = title;

        const userEl = document.createElement("p");
        userEl.textContent = `by ${user}`;

        const time = document.createElement("p");
        time.textContent = new Date(item.created_at).toLocaleString();

        card.appendChild(h3);
        card.appendChild(userEl);
        card.appendChild(time);
        return card;
    };

    const loadModels = async () => {
        grid.innerHTML =
            `<p style="text-align:center; color:var(--muted); padding:20px;">読み込み中...</p>`;

        try {
            const res = await fetch("/api/catalog");
            const data = await res.json();
            grid.innerHTML = "";

            if (!data.ok) {
                grid.innerHTML = "<p style='text-align:center; color:red;'>データの取得に失敗しました。</p>";
                return;
            }

            const models = data.models || [];
            if (models.length === 0) {
                grid.innerHTML =
                    "<p style='text-align:center; color:var(--muted);'>まだ登録されたモデルがありません。</p>";
                return;
            }

            models.forEach((item) => grid.appendChild(renderCard(item)));
        } catch (err) {
            console.error(err);
            grid.innerHTML = `<p style="color:red; text-align:center;">エラー: ${err.message}</p>`;
        }
    };

    loadModels();
});
