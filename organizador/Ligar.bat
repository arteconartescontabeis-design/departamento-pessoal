@echo off
rem Liga o Organizador e abre o painel no navegador
cd /d "%~dp0"
start "Organizador de Documentos" cmd /k python app.py
timeout /t 3 /nobreak >nul
start "" http://localhost:8767
