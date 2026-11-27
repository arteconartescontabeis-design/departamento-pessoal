@echo off
rem Liga o Organizador e abre o painel no navegador
cd /d "%~dp0"
rem encerra qualquer execucao antiga: e ela que faz o painel mostrar versao velha
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul
start "Organizador de Documentos" cmd /k python app.py
timeout /t 4 /nobreak >nul
start "" http://localhost:8767
