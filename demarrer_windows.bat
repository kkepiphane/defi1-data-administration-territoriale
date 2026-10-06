@echo off
rem Demarrage du tableau de bord sous Windows : double-cliquer sur ce fichier.
rem Premiere fois : environnement Python local (.venv) + bibliotheques. Ensuite : demarrage direct.
setlocal
chcp 65001 >nul
title Mobilité et sécurité routière - Togo
cd /d "%~dp0"
set "VENV_PY=.venv\Scripts\python.exe"

echo.
echo   Mobilité et sécurité routière au Togo - tableau de bord
echo   --------------------------------------------------------
echo.

if not exist "app.py" goto not_extracted

if exist "%VENV_PY%" (
    echo   [1/3] Environnement Python local déjà prêt.
    goto deps
)
call :find_python
if not defined PY goto no_python
echo   [1/3] Première utilisation : création de l'environnement Python local .venv - environ 20 secondes...
%PY% -m venv .venv
if errorlevel 1 goto venv_error

:deps
fc /b requirements.txt .venv\requirements.ok >nul 2>&1
if not errorlevel 1 (
    echo   [2/3] Bibliothèques déjà installées.
    goto run
)
echo   [2/3] Installation des bibliothèques : 2 à 5 minutes la première fois, connexion internet requise...
echo.
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_error
copy /y requirements.txt .venv\requirements.ok >nul
echo.

:run
echo   [3/3] Démarrage du tableau de bord...
echo.
"%VENV_PY%" app.py %*
if errorlevel 1 pause
exit /b

:find_python
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3" && exit /b
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
exit /b

:not_extracted
echo   [Erreur] Le dossier n'est pas décompressé.
echo   Faites un clic droit sur l'archive .zip, choisissez "Extraire tout",
echo   puis double-cliquez sur demarrer_windows.bat dans le dossier extrait.
echo.
pause
exit /b 1

:no_python
echo   [Erreur] Python 3.10 ou plus est introuvable.
echo   Installez-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH",
echo   puis double-cliquez à nouveau sur ce fichier.
echo.
pause
exit /b 1

:venv_error
echo   [Erreur] Impossible de créer l'environnement Python local .venv.
echo   Si le chemin du dossier est très long, déplacez-le plus près de la racine, par exemple C:\securite-routiere-togo
rmdir /s /q .venv 2>nul
echo.
pause
exit /b 1

:pip_error
echo.
echo   [Erreur] L'installation des bibliothèques a échoué.
echo   Vérifiez la connexion internet puis relancez ce fichier : l'installation reprendra.
echo   Si le message mentionne "Long Path", déplacez le dossier plus près de la racine, par exemple C:\securite-routiere-togo
echo.
pause
exit /b 1
