@echo off
setlocal
cd /d "%~dp0"

set "PY="

where py >nul 2>nul
if not errorlevel 1 set "PY=py"

if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  for %%V in (313 312 311 310 39) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  )
)

if not defined PY (
  echo.
  echo [ERROR] Python 3 not found on this machine.
  echo Install Python 3, or run manually:  python stats\pull_stats.py
  echo.
  if "%~1"=="" pause
  exit /b 1
)

chcp 65001 >nul

"%PY%" "stats\pull_stats.py" %*
set "RC=%errorlevel%"

echo.
if "%~1"=="" pause
exit /b %RC%
