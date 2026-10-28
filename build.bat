@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] checking PyInstaller ...
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo     installing ...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo     retry with mirror ...
        python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
    )
)

echo [2/3] generating icon ...
python tools\make_icon.py
if errorlevel 1 goto :fail

echo [3/3] building ...
python -m PyInstaller --noconfirm --clean pdftrans.spec
if errorlevel 1 goto :fail

echo.
echo done: dist\PDFTrans\PDFTrans.exe
pause
exit /b 0

:fail
echo.
echo build failed, see the errors above.
pause
exit /b 1
