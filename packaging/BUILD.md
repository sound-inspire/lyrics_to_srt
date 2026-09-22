# exe版のビルド手順（Windows）

配布用のexe版（`lyrics_to_srt.exe` を含むフォルダ）を作る手順です。
利用者向けの手順ではありません。開発者がリリースを作るときに使います。

## 1. ビルド環境を用意する

```bash
python -m venv .venv-build
.venv-build\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

## 2. ffmpeg.exe を用意する

`packaging/ffmpeg.exe` に、Windows用の静的ビルドの `ffmpeg.exe` を置きます。
（[gyan.dev](https://www.gyan.dev/ffmpeg/builds/) の release essentials 版などから取得。
このファイルはGitには含めません＝ `.gitignore` 済み）

## 3. ビルドする

```bash
pyinstaller packaging/lyrics_to_srt.spec --distpath packaging/dist --workpath packaging/build
```

`packaging/dist/lyrics_to_srt/` にフォルダが生成されます。中に
`lyrics_to_srt.exe`・`ffmpeg.exe`・依存DLL一式が入っています。

## 4. 動作確認

```bash
packaging\dist\lyrics_to_srt\lyrics_to_srt.exe sample_重さの置き場所_lyrics.txt "曲.wav"
```

- 生成されたSRTのタイムスタンプが、Python版で同じ入力を処理した結果と一致することを確認する
- PATHから一時的にffmpegを外した状態でも動くこと（同梱ffmpegが使われていること）を確認する
- 初回実行時にWhisperモデル（`medium`）のダウンロードが走ることを確認する（要ネット接続）

## 5. 配布物を作る

`packaging/dist/lyrics_to_srt/` フォルダに `使い方.txt`（README.mdの使い方部分）を追加してから
zip化し、`lyrics_to_srt-win64-vX.Y.zip` のような名前にします。

**このzipはGitリポジトリにはコミットせず、GitHubの Releases に添付して公開します。**
（バイナリでリポジトリを肥大化させないため）
