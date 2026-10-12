@echo off
chcp 65001 >nul
rem 使い方: 本編 WAV・ボーカルステム WAV・SRT をこの bat にまとめてドラッグ＆ドロップ（順不同）
rem   再生は本編、波形はステム（名前に Vocals を含む WAV）。片方だけでも開ける
rem   SRT を省略すると本編と同じ場所の 作品名.srt を開く
rem   保存は画面の「作品名」欄の名前で、本編と同じフォルダへ
set PYTHONIOENCODING=utf-8
python "%~dp0srt_editor\srt_edit_server.py" %*
pause
