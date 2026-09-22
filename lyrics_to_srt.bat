@echo off
chcp 65001 >nul
rem 使い方: 歌詞txt と WAV をこの bat にまとめてドラッグ＆ドロップ（順不同）
rem   ボーカルステム（名前に Vocals を含む WAV）… あれば分離を省略して速くなる
rem   ミックス WAV … ステムが無ければ分離に使い、ステムと一緒なら拍の測定に使う
rem   WAV の名前に 123bpm のようにテンポを書くと、ステムだけでも拍に合わせられる
set PYTHONIOENCODING=utf-8
python "%~dp0lyrics_to_srt.py" %*
pause
