# PyInstaller spec for the Windows exe of the SRT editor (srt_edit.exe).
#
# 標準ライブラリだけで動くため1ファイルにまとめる。画面(srt_editor.html)を同梱する。
# lyrics_to_srt の配布フォルダ(dist/lyrics_to_srt/)に同居させる。ビルド方法は BUILD.md を参照。
#
# 実行例:
#   pyinstaller packaging/srt_edit.spec --distpath packaging/dist/lyrics_to_srt --workpath packaging/build

import os

ROOT = os.path.dirname(os.path.abspath(SPEC))
EDITOR = os.path.join(os.path.dirname(ROOT), "srt_editor")

a = Analysis(
    [os.path.join(EDITOR, "srt_edit_server.py")],
    pathex=[EDITOR],
    binaries=[],
    datas=[(os.path.join(EDITOR, "srt_editor.html"), ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "torch", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="srt_edit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
