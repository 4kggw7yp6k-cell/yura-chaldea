YURA Chaldea — GitHub Pages公開手順

1. GitHubにログインし、新しいRepositoryを作成
   例: yura-chaldea

2. このZIPを展開し、中身のファイルをRepositoryのルートへすべてアップロード
   index.html が一番上の階層にある状態にしてください。

3. Repositoryの
   Settings → Pages
   を開く

4. Build and deployment
   Source: Deploy from a branch
   Branch: main
   Folder: / (root)
   を選び Save

5. 少しして表示される公開URLをiPhoneのSafariで開く

6. Safariの共有ボタン →「ホーム画面に追加」

7. ホーム画面の YURA Chaldea アイコンから起動

注意:
- 必ずHTTPSの公開URLをSafariで開いてください。
- Safariの通常タブで一度開いてからホーム画面に追加してください。
- データはlocalStorageに保存されるため、SafariのWebサイトデータ削除や再インストールで消える可能性があります。
- OpenAI APIキーをapp.jsやHTMLに直接書かないでください。

Ver.0.01機能:
- 聖晶石 / 呼符 / 聖晶片
- 召喚回数換算
- 天井まで残り
- 履歴
- 簡易ユラさん相談
- PWA / ホーム画面追加
- オフラインキャッシュ
