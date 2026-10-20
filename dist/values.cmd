@echo off
setlocal
set "PYZ=%~dp0values.pyz"
where py >nul 2>nul
if not errorlevel 1 goto usepy
where python >nul 2>nul
if not errorlevel 1 goto usepython
echo 需要先安装 Python 3.9 或更高版本：https://www.python.org/downloads/
exit /b 1

:usepy
py "%PYZ%" %*
exit /b %errorlevel%

:usepython
python "%PYZ%" %*
exit /b %errorlevel%
