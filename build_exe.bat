@echo off
echo ==========================================
echo  AISBench-Prefix-Tools - EXE Build Script
echo ==========================================
echo.

pip install -r requirements.txt

echo.
echo Building EXE...
pyinstaller --noconfirm --onefile --windowed --name "AISBench-Prefix-Tools" --add-data "requirements.txt;." main.py

echo.
echo Build complete! Check dist\ folder for AISBench-Prefix-Tools.exe
pause
