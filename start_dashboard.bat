@echo off
title Tandy.inc Control Dashboard Server
echo ==================================================
echo  🚀 Tandy.inc Control Dashboard を起動しています...
echo  🔗 ブラウザで http://localhost:3000 を開きます。
echo ==================================================
cd /d "%~dp0Outputs\dashboard"
start "" "http://localhost:3000"
node server.js
pause
