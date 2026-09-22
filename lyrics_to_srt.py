"""WAV + 歌詞テキスト → SRT

usage:
    python lyrics_to_srt.py ファイル… （順不同。拡張子とファイル名で役割を自動判別）
      歌詞.txt              必須。[Intro] などのセクション行と空行は無視し、残りの1行＝字幕1枚
      曲 (Vocals).wav       ボーカルステム（名前に "vocal" を含む WAV）。あれば分離を省略して速くなる
      曲.wav                ミックス音源。ステムが無ければ demucs でボーカルを分離する（約4分余計にかかる）
                            ステムと一緒に渡すと、拍の位置の測定に使う
      出力.srt              省略時は WAV と同じ場所に 曲.srt（"(Vocals)" や "_123bpm" は名前から除く）

テンポ: WAV のファイル名に "123bpm" のように書くと使う（任意）。
  書いてあれば音声で検証し、食い違えば警告して実測値を使う。
  書いていなくても、ミックス音源があれば実測する。ステムだけ＆テンポ記載なしなら拍への吸着は省略。

処理:
  1. ステムが無ければ demucs でボーカルだけを分離（一時ファイルは読み込み後に自動削除）
  2. Whisper で自由に聞き取り、1秒以上の空白＝間奏の位置を得る
  3. 間奏で区切り、ブロックごとに歌詞を強制アライメント（照合器が間奏を詰めてしまうのを防ぐ）
  4. ブロック先頭行の開始を、ボーカルの無音明け（無ければ息継ぎの谷明け）に合わせる
  5. （既定は無効）各行の開始を、±SNAP_MAX 以内なら最寄りの8分音符の拍位置に吸着
  6. 全行を SHIFT 秒だけ前倒し（文字を読む時間の分、声より少し先に出す）

必要: ffmpeg, pip install torch stable-ts demucs soundfile librosa
"""
import re, sys, os, difflib, subprocess, tempfile, shutil
import numpy as np
import stable_whisper

# exe化(PyInstaller)されているときは、同梱した ffmpeg.exe を使う。
# PyInstaller 6系はonedirでも実データを _internal 配下に置くため、
# 実行フォルダ直下ではなく sys._MEIPASS（同梱データの実体）を見る。
# 通常のPython実行時は今まで通りPATH上の ffmpeg を使う。
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _bundled = os.path.join(_base, "ffmpeg.exe")
    FFMPEG = _bundled if os.path.exists(_bundled) else "ffmpeg"
else:
    FFMPEG = "ffmpeg"

MODEL = "medium"
GAP_SPLIT = 1.0   # 聞き取り区間の間にこれ以上の空白があれば間奏とみなして区切る
LEAD = 0.5        # 区切り位置を歌い出しの少し前に置く
OUTLIER = 2.0     # 行内でこれ以上離れた文字は外れ値
TAIL = 0.4        # 語尾の余韻
GRID_DIV = 2      # 拍の格子の細かさ（2 = 8分音符）
SNAP_MAX = 0      # 格子への吸着を行う最大のずれ（秒）。0で無効。
                  # 検証(重さの置き場所)では 0.08 にすると発声とのずれが 60→82ms に悪化したため既定は無効
                  # （行頭は拍より食って入ることが多く、隣の格子へ引き寄せてしまう）
BPM_TOL = 0.5     # ファイル名のテンポと実測の許容差（BPM）
SHIFT = 0.1       # 全行の前倒し（秒）

# 引数の振り分け
lyr = mix = stem = out = None
for p in sys.argv[1:]:
    ext = os.path.splitext(p)[1].lower()
    if ext == ".txt":
        lyr = p
    elif ext == ".srt":
        out = p
    elif "vocal" in os.path.basename(p).lower():
        stem = p
    else:
        mix = p
if not lyr or not (mix or stem):
    sys.exit(__doc__)

bpm_tag = None
for p in (stem, mix):
    m = p and re.search(r"(\d+(?:\.\d+)?)\s*bpm", os.path.basename(p), re.I)
    if m:
        bpm_tag = float(m.group(1))
        break

if not out:
    base = os.path.splitext(stem or mix)[0]
    d, name = os.path.split(base)
    name = re.sub(r"[\s_\-]*[\(\[（]?\s*(lead\s*)?vocals?\s*[\)\]）]?\s*$", "", name, flags=re.I) or name
    name = re.sub(r"[\s_\-]*\d+(?:\.\d+)?\s*bpm", "", name, flags=re.I) or name
    out = os.path.join(d, name + ".srt")

lines = [l.strip() for l in open(lyr, encoding="utf-8-sig")
         if l.strip() and not re.fullmatch(r"\[.*\]", l.strip())]
norm = lambda s: re.sub(r"[\s、。，．,.!?！？]", "", s)
print(f"歌詞 {len(lines)} 行 / ステム: {stem or 'なし'} / ミックス: {mix or 'なし'} / テンポ記載: {bpm_tag or 'なし'}")

# 0. ボーカル分離（ステムならスキップ）
tmp = None
if stem:
    print("ボーカルステムを使用 → 分離をスキップ")
    wav = stem
else:
    tmp = tempfile.mkdtemp(prefix="lyrics_to_srt_")
    print("ボーカル分離中（demucs）…")
    # exe化すると sys.executable がexe自身になり `-m demucs` が使えないため、
    # サブプロセスではなくdemucsのPython APIを直接呼ぶ（挙動は同じ）。
    from demucs.separate import main as demucs_main
    demucs_main(["--two-stems", "vocals", "-o", tmp, mix])
    wav = os.path.join(tmp, "htdemucs", os.path.splitext(os.path.basename(mix))[0], "vocals.wav")

def load16k(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)

audio = load16k(wav)
if tmp:
    shutil.rmtree(tmp, ignore_errors=True)  # 分離したボーカルは読み込んだら不要なので一時フォルダごと消す
SR = 16000

model = stable_whisper.load_model(MODEL, device="cpu")

# 1. 自由聞き取りで間奏の位置を得る
print("聞き取り中…")
r = model.transcribe(audio, language="ja", verbose=None)
segs = [{"start": s.start, "end": s.end, "text": s.text} for s in r.segments]

# 2. 間奏の直後の区間が、どの歌詞行から始まるかを文字列の類似度で決める
cuts = [(0.0, 0)]  # (音声の区切り秒, 最初の行番号)
last_line = 0
for a, b in zip(segs, segs[1:]):
    if b["start"] - a["end"] < GAP_SPLIT:
        continue
    head = norm(b["text"])
    best, best_i = 0, None
    for i in range(last_line + 1, len(lines)):
        L = norm("".join(lines[i:i + 2]))  # 2行ぶんで照合（くり返しサビの取り違え防止）
        sc = difflib.SequenceMatcher(None, L, head[:len(L)]).ratio()
        if sc > best:
            best, best_i = sc, i
    if best_i is not None and best >= 0.5:
        cuts.append((max(a["end"], b["start"] - LEAD - 1.0), best_i))
        last_line = best_i
        print(f"区切り {cuts[-1][0]:.2f}s → 行{best_i+1}「{lines[best_i]}」(類似度{best:.2f})")

# 3. ブロックごとに照合
spans = [None] * len(lines)
for k, (t0, li0) in enumerate(cuts):
    t1 = cuts[k + 1][0] if k + 1 < len(cuts) else len(audio) / SR
    li1 = cuts[k + 1][1] if k + 1 < len(cuts) else len(lines)
    blk = lines[li0:li1]
    print(f"照合中: 行{li0+1}〜{li1}")
    res = model.align(audio[int(t0 * SR):int(t1 * SR)], "\n".join(blk), language="ja")
    owner = [i for i, l in enumerate(blk) for _ in norm(l)]
    per = [[] for _ in blk]
    pos = 0
    for w in res.all_words():
        t = norm(w.word)
        if not t:
            continue
        per[owner[min(pos, len(owner) - 1)]].append((w.start + t0, w.end + t0, len(t)))
        pos += len(t)
    for j, ws in enumerate(per):
        clusters, cur = [], [ws[0]]
        for a, b in zip(ws, ws[1:]):
            if b[0] - a[1] >= OUTLIER:
                clusters.append(cur); cur = []
            cur.append(b)
        clusters.append(cur)
        c = max(clusters, key=lambda c: sum(x[2] for x in c))
        spans[li0 + j] = [c[0][0], c[-1][1]]

def set_start(li, t):
    spans[li][0] = t
    if li > 0:
        spans[li - 1][1] = min(spans[li - 1][1], t)

# 4. ブロック先頭行の開始を、ボーカルの無音明け（音量の立ち上がり）に合わせる
H = int(SR * 0.05)
n = len(audio) // H
db = 20 * np.log10(np.sqrt((audio[:n * H].reshape(n, H) ** 2).mean(1)) + 1e-9)
voiced = db > db.max() - 25
for _, li in cuts:
    s = spans[li][0]
    lo, hi = int((s - 1.5) / 0.05), int((s + 1.5) / 0.05)
    best = None
    for f in range(max(lo, 4), min(hi, n - 4)):
        # 0.2秒以上の無音 → 0.2秒以上の有音 に切り替わる点
        if not voiced[f - 4:f].any() and voiced[f:f + 4].all():
            if best is None or abs(f * 0.05 - s) < abs(best - s):
                best = f * 0.05
    how = "無音明け"
    if best is None and li > 0:
        # 完全な無音がない（前の行の余韻とつながる）場合：最も深い音量の谷の直後
        w = db[max(lo, 0):min(hi, n)]
        sm = np.convolve(w, np.ones(4) / 4, "same")  # 子音の一瞬の落ち込みを無視し、息継ぎの幅のある谷を拾う
        m = int(np.argmin(sm))
        while m + 1 < len(w) and w[m + 1] <= w[m] + 3:
            m += 1
        if np.median(w) - w[m] >= 10:
            f = max(lo, 0) + m
            best, how = (f + 1) * 0.05, "息継ぎの谷明け"
    if best is not None:
        print(f"行{li+1} 開始 {s:.2f} → {best:.2f}（{how}）")
        set_start(li, best)

# 5. 拍の格子（1拍の長さ period と、拍の位置 phase）を求め、行頭を吸着
def grid_from_mix(path):
    """ミックス音源の拍を検出し、直線近似で1拍の長さと位相を得る"""
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    _, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    bt = np.asarray(beats)
    if len(bt) < 16:
        return None
    per = np.median(np.diff(bt))
    k = np.round((bt - bt[0]) / per)
    period, phase = np.polyfit(k, bt, 1)
    return period, phase

def grid_from_vocals(bpm):
    """テンポ既知のとき、ボーカルの発声の立ち上がりが最も揃う 1拍の長さと位相を探す"""
    import librosa
    on = librosa.onset.onset_detect(y=audio, sr=SR, units="time")
    best = None
    for b in np.arange(bpm - 1.0, bpm + 1.0001, 0.01):
        g = 60 / b / GRID_DIV
        z = np.exp(2j * np.pi * on / g).mean()  # 格子に揃うほど |z| が1に近づく
        if best is None or abs(z) > best[0]:
            best = (abs(z), b, (np.angle(z) / (2 * np.pi)) % 1 * g)
    score, b, ph = best
    return 60 / b, ph, score

grid = None
if mix:
    print("拍の位置を測定中…")
    g = grid_from_mix(mix)
    if g:
        period, phase = g
        bpm_meas = 60 / period
        if bpm_tag:
            # 倍・半分のテンポに取り違えていたら、記載テンポに合わせて直す
            for f in (2, 0.5):
                if abs(bpm_meas * f - bpm_tag) < abs(bpm_meas - bpm_tag):
                    period /= f; bpm_meas *= f
            if abs(bpm_meas - bpm_tag) > BPM_TOL:
                print(f"⚠ ファイル名のテンポ {bpm_tag} と実測 {bpm_meas:.2f} が食い違います → 実測値を使います")
        grid = (period, phase)
        print(f"テンポ {bpm_meas:.2f} BPM（ミックスから実測）")
elif bpm_tag:
    print("拍の位置を推定中（記載テンポ＋ボーカルの発声位置）…")
    period, phase, score = grid_from_vocals(bpm_tag)
    bpm_meas = 60 / period
    if score < 0.2:
        print(f"⚠ 発声が拍に揃っていません（一致度 {score:.2f}）→ 拍への吸着を省略します")
    else:
        if abs(bpm_meas - bpm_tag) > BPM_TOL:
            print(f"⚠ ファイル名のテンポ {bpm_tag} と、発声から推定した {bpm_meas:.2f} が食い違います → 推定値を使います")
        grid = (period, phase)
        print(f"テンポ {bpm_meas:.2f} BPM（一致度 {score:.2f}）")
else:
    print("テンポ情報なし（ステムのみ・ファイル名にbpm記載なし）→ 拍への吸着を省略")

if grid and SNAP_MAX > 0:
    period, phase = grid
    g = period / GRID_DIV
    moved = []
    for i, sp in enumerate(spans):
        p = phase + round((sp[0] - phase) / g) * g
        if abs(p - sp[0]) <= SNAP_MAX:
            if abs(p - sp[0]) >= 0.005:
                moved.append(f"行{i+1} {(p - sp[0]) * 1000:+.0f}ms")
            set_start(i, p)
    print(f"拍に吸着: {len(moved)}行を移動 / 範囲外で据え置き: "
          f"{sum(abs(phase + round((sp[0]-phase)/g)*g - sp[0]) > 0.005 for sp in spans)}行")
    if moved:
        print("  " + ", ".join(moved))

for i, sp in enumerate(spans):
    nxt = spans[i + 1][0] if i + 1 < len(spans) else sp[1] + TAIL
    if sp[1] < nxt:
        sp[1] = min(sp[1] + TAIL, nxt)

# 6. 全行を前倒し
for sp in spans:
    sp[0] = max(0.0, sp[0] - SHIFT)
    sp[1] = max(sp[0], sp[1] - SHIFT)

def ts(x):
    ms = int(round(x * 1000))
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"

with open(out, "w", encoding="utf-8") as f:
    for i, (l, (s, e)) in enumerate(zip(lines, spans)):
        f.write(f"{i+1}\n{ts(s)} --> {ts(e)}\n{l}\n\n")
        print(f"{i+1:2} {ts(s)} {ts(e)} {e-s:5.2f}s {l}")

print(f"書き出し: {out}（前倒し {SHIFT}s 込み）")
