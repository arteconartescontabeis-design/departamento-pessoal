@echo off
rem Atualiza o Organizador com o ZIP mais recente do Downloads (organizador-v*.zip)
cd /d "%~dp0"

echo Encerrando o Organizador se estiver aberto...
taskkill /f /im python.exe >nul 2>&1

set "ZIP="
for /f "delims=" %%f in ('dir /b /o-d "%USERPROFILE%\Downloads\organizador-v*.zip" 2^>nul') do (
    if not defined ZIP set "ZIP=%%f"
)
if not defined ZIP (
    echo Nenhum arquivo organizador-v*.zip encontrado no Downloads.
    echo Baixe o ZIP enviado no chat e rode este Atualizar de novo.
    pause
    exit /b 1
)

echo Atualizando com: %ZIP%
rem o ponto no final evita que a barra invertida final engula a aspa
tar -xf "%USERPROFILE%\Downloads\%ZIP%" -C "%~dp0."
if errorlevel 1 (
    echo Falha ao extrair o ZIP.
    pause
    exit /b 1
)

echo Instalando dependencias...
pip install -q -r requirements.txt

echo.
findstr /C:"VERSAO = " app.py
echo Atualizado. Use o Ligar.bat para abrir.
pause
