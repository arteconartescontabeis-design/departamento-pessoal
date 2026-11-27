@echo off
rem Liga o Organizador e abre o painel quando ele estiver respondendo
cd /d "%~dp0"

rem encerra qualquer execucao antiga: e ela que faz o painel mostrar versao velha
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

start "Organizador de Documentos" cmd /k python app.py

echo Aguardando o aplicativo subir (ate 60s)...
set /a tentativas=0
:espera
timeout /t 1 /nobreak >nul
curl -s -o nul http://localhost:8767/api/config && goto pronto
set /a tentativas+=1
if %tentativas% lss 60 goto espera
echo.
echo O aplicativo nao respondeu em 60s. Veja a janela "Organizador de Documentos":
echo se houver mensagem de erro, envie um print para o Claude.
pause
exit /b 1

:pronto
start "" http://localhost:8767
