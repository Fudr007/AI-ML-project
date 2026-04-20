@echo off
setlocal

:: Zkusíme různé způsoby, jak zavolat Python
set PY=none

python --version >nul 2>&1 && set PY=python
if "%PY%"=="none" (
    py --version >nul 2>&1 && set PY=py
)

if "%PY%"=="none" (
    echo [CHYBA] Python neni v PATH. Zkousim najit v typickych slozkach...
    if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set PY="%LocalAppData%\Programs\Python\Python310\python.exe"
    if exist "C:\Python310\python.exe" set PY="C:\Python310\python.exe"
)

if "%PY%"=="none" (
    echo [ERROR] Python nebyl nalezen! Musis ho nainstalovat nebo pridat do PATH.
    pause
    exit /b
)

echo Pouzivam: %PY%
%PY% -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
python app.py
pause