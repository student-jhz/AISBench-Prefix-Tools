@echo off
echo ==========================================
echo  AISBench Deployer - EXE Build Script
echo ==========================================
echo.

pip install -r requirements.txt

echo.
echo Building EXE...
pyinstaller --noconfirm --onefile --windowed --name "AISBenchDeployer" --add-data "requirements.txt;." main.py

echo.
echo Build complete! Check dist\ folder for AISBenchDeployer.exe
pause
