@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.12 for Windows from python.org, including the Python launcher.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "import tkinter" >nul 2>&1
if errorlevel 1 goto missingtk
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)"
if errorlevel 1 goto failed
echo Setup finished. Double-click run.bat to start.
pause
exit /b 0
:missingtk
echo Python's window interface is missing.
echo Open the Python installer, choose Modify, enable "tcl/tk and IDLE", and install.
echo Then run setup.bat again.
pause
exit /b 1
:failed
echo Setup failed. Read the error above.
pause
exit /b 1
