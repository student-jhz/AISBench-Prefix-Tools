@echo off
echo ==========================================
echo  AISBench-Prefix-Tools - EXE Build Script
echo ==========================================
echo.

pip install -r requirements.txt

echo.
echo Building EXE...
pyinstaller --noconfirm --onefile --windowed --name "AISBench-Prefix-Tools" --icon=app.ico --add-data "requirements.txt;." --add-data "app.ico;." --add-data "aisbench_auto_tools_prefix;aisbench_auto_tools_prefix" main.py

echo.
echo Build complete! Check dist\ folder for AISBench-Prefix-Tools.exe
pause
