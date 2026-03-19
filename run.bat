@echo on
cd /d "%~dp0"
 
python --version
python -m pip show requests >nul 2>&1 || python -m pip install requests
start pythonw app.py