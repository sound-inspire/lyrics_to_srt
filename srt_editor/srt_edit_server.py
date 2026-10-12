"""WAV + SRT を読み込み、波形つきで字幕を確認・編集する画面を開く。

usage:
    python srt_edit_server.py 曲.wav [曲 (Vocals).wav] [字幕.srt] [--title 作品名] [--port 8030] [--no-browser]
      曲.wav            本編（ミックス）。再生に使う
      曲 (Vocals).wav   ボーカルステム（名前に "vocal" を含む WAV）。波形の表示に使う（任意）
                        どちらか一方だけなら、それを再生にも波形にも使う
      字幕.srt          省略時は本編と同じ場所の 作品名.srt があれば読む（無ければ空で開く）
      --title           保存名（作品名）の初期値。省略時は本編の名前から "(Vocals)" や "_123bpm" を除いたもの

保存先は本編（無ければステム）と同じフォルダの「作品名.srt」。同名があるときは画面で上書きを確認する。
ローカル（127.0.0.1）だけで待ち受ける。標準ライブラリのみで動く。
"""
import argparse, json, os, re, socket, sys, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# exe化(PyInstaller)されているときは、同梱した srt_editor.html を sys._MEIPASS から読む
FROZEN = getattr(sys, "frozen", False)
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))) if FROZEN \
    else os.path.dirname(os.path.abspath(__file__))
if FROZEN:
    # ダブルクリック起動でエラー終了したとき、窓が即座に閉じて内容が読めないのを防ぐ
    import atexit
    atexit.register(lambda: input("\n終了するには Enter を押してください…"))
# 出力をファイルへ回すと cp932 になるため、書けない文字は置き換えて続ける
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

BAD = r'[\\/:*?"<>|\r\n\t]'


def title_from_wav(path):
    name = os.path.splitext(os.path.basename(path))[0]
    # テンポ表記を先に除く（"曲 (Vocals)_120bpm" の "(Vocals)" が末尾に来るように）
    name = re.sub(r"[\s_\-]*\d+(?:\.\d+)?\s*bpm", "", name, flags=re.I) or name
    name = re.sub(r"[\s_\-]*[\(\[（]?\s*(lead\s*)?vocals?\s*[\)\]）]?\s*$", "", name, flags=re.I) or name
    return name.strip()


def clean_title(t):
    t = re.sub(BAD, "", (t or "").strip())
    t = re.sub(r"\.srt$", "", t, flags=re.I).strip(" .")
    return t


def free_port(start):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    sys.exit("空いているポートが見つかりません")


def make_handler(cfg):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "srt_editor.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/info":
                return self.send(200, {
                    "wav": os.path.basename(cfg["wav"]),
                    "stem": os.path.basename(cfg["stem"]) if cfg["stem"] else "",
                    "srt": os.path.basename(cfg["srt"]) if cfg["srt"] else "",
                    "dir": os.path.dirname(cfg["wav"]),
                    "title": cfg["title"],
                })
            if path in ("/api/audio", "/api/stem"):
                src = cfg["stem"] if path == "/api/stem" and cfg["stem"] else cfg["wav"]
                with open(src, "rb") as f:
                    return self.send(200, f.read(), "audio/wav")
            if path == "/api/srt":
                if cfg["srt"] and os.path.exists(cfg["srt"]):
                    with open(cfg["srt"], encoding="utf-8-sig") as f:
                        return self.send(200, f.read(), "text/plain; charset=utf-8")
                return self.send(200, "", "text/plain; charset=utf-8")
            self.send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/save":
                return self.send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                req = json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                return self.send(400, {"error": "JSON を読めません"})
            title = clean_title(req.get("title"))
            if not title:
                return self.send(400, {"error": "作品名を入れてください"})
            text = req.get("text") or ""
            if not text.strip():
                return self.send(400, {"error": "字幕が空です"})
            out = os.path.join(os.path.dirname(cfg["wav"]), title + ".srt")
            same = cfg["srt"] and os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(cfg["srt"]))
            if os.path.exists(out) and not req.get("overwrite"):
                return self.send(409, {"exists": True, "path": out, "same": bool(same)})
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            cfg["srt"], cfg["title"] = out, title
            print(f"保存: {out}", flush=True)
            self.send(200, {"path": out, "name": os.path.basename(out)})
    return H


def main():
    ap = argparse.ArgumentParser(description="WAV と SRT を波形つきで確認・編集する")
    ap.add_argument("files", nargs="+", help="曲.wav と 字幕.srt（順不同）")
    ap.add_argument("--title")
    ap.add_argument("--port", type=int, default=8030)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    wavs = [os.path.abspath(p) for p in a.files if p.lower().endswith(".wav")]
    srt = next((os.path.abspath(p) for p in a.files if p.lower().endswith(".srt")), None)
    for p in wavs:
        if not os.path.exists(p):
            sys.exit("WAV が見つかりません: " + p)
    stems = [p for p in wavs if "vocal" in os.path.basename(p).lower()]
    mixes = [p for p in wavs if p not in stems]
    if not wavs or len(stems) > 1 or len(mixes) > 1:
        sys.exit("WAV は本編1つ・ステム1つまで渡せます（ステムは名前に vocal を含むもの）")
    wav = mixes[0] if mixes else stems[0]          # 再生と保存先の基準
    stem = stems[0] if mixes and stems else None   # 波形用（本編と別にあるときだけ）
    title = clean_title(a.title) or title_from_wav(wav)
    if not srt:
        cand = os.path.join(os.path.dirname(wav), title + ".srt")
        srt = cand if os.path.exists(cand) else None
    if srt and not os.path.exists(srt):
        sys.exit("SRT が見つかりません: " + srt)

    cfg = {"wav": wav, "stem": stem, "srt": srt, "title": title}
    port = free_port(a.port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg))
    url = f"http://127.0.0.1:{port}/"
    print(f"SRT エディタ: {url}\n  再生: {wav}\n  波形: {stem or wav}\n  SRT: {srt or '（なし・空で開く）'}\n  作品名: {title}\n終了は Ctrl+C", flush=True)
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
