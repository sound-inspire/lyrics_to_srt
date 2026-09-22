# PyInstaller spec for the Windows exe distribution of lyrics_to_srt.
#
# ビルド方法は BUILD.md を参照。
#
# 実行例:
#   pyinstaller packaging/lyrics_to_srt.spec

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.dirname(ROOT)
FFMPEG_EXE = os.path.join(ROOT, "ffmpeg.exe")

datas = []
if os.path.exists(FFMPEG_EXE):
    datas.append((FFMPEG_EXE, "."))
# openai-whisper はパッケージ同梱の静的アセット(mel_filters.npz等)を
# importlib経由で読むため、PyInstallerの自動検出に乗らない。明示的に含める。
datas += collect_data_files("whisper")

a = Analysis(
    [os.path.join(PROJECT_ROOT, "lyrics_to_srt.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["demucs.separate"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lyrics_to_srt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="lyrics_to_srt",
)
