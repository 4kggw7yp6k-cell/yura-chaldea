YURA Chaldea Ver.0.03 — 自動PU更新版

【仕組み】
FGO公式のお知らせ一覧
        ↓
GitHub Actions（1時間ごと）
        ↓
scripts/update_pickup.py
        ↓
pickup.json が「新しいPUのときだけ」更新・自動コミット
        ↓
GitHub Pages が再デプロイ
        ↓
YURA Chaldea の「最新ピックアップ」が自動更新

【APIキー】
不要です。OpenAI APIもX APIも使いません。
確認先はFate/Grand Order日本版公式サイトです。

【既存データ】
localStorageキーは yuraChaldeaStateV001 のままです。
聖晶石・呼符・聖晶片・履歴・目標はVer.0.02から引き継がれます。

【GitHubで追加するもの】
通常ファイル:
  index.html
  style.css
  app.js
  sw.js
  pickup.json
  requirements.txt
  icon類 / manifest.webmanifest はFull版利用時のみ

フォルダ:
  scripts/update_pickup.py
  .github/workflows/update-pickup.yml

iPhone Safariではフォルダの一括アップロードが難しい場合があります。
その場合、GitHubの「Create new file」で以下のパスをそのままファイル名欄へ入力するとフォルダごと作れます:
  scripts/update_pickup.py
  .github/workflows/update-pickup.yml

【初回動作確認】
Actions → Update FGO pickup → Run workflow
を1回手動実行できます。
緑のチェックになれば完成です。

【注意】
FGO公式ページのHTML構造が将来大きく変わった場合、抽出スクリプトの調整が必要になることがあります。
サーヴァント名は誤認を避けるため保守的に抽出し、判別できない場合は公式リンクを表示します。
