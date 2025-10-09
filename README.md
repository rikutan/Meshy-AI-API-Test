# 性格診断 検証

## 実行方法
1. Flaskを実行する仮想環境を作成
```
conda create -n 「任意の仮想環境名」
```
2. 仮想環境を有効化
```
conda activate 「仮想環境名」
```
3. 依存関係をインストール（flaskなどのインストールもこれ一回で出来る）
```
pip install -r requirements.txt
```
4. 「.env」ファイルをプロジェクト直下に作成をして自身の API Key を設定
```
MESHY_API_KEY=MeshyのAPI Key
GEMINI_API_KEY=GeminiのAPI Key

FLASK_DEBUG=1
FLASK_RUN_PORT=5173

```
