@echo off
REM 3. Create a Python virtual environment called dcVenv
set VENV=dcVenv
if not exist %VENV% (
    python -m venv %VENV%
    echo Virtual environment 'dcVenv' created.
) else (
    echo Virtual environment 'dcVenv' already exists.
)

REM 4. Activate the dcVenv virtual environment
call %VENV%\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo Failed to activate the virtual environment 'dcVenv'.
    exit /b 1
) else (
    echo Activated virtual environment 'dcVenv'.
)

REM 5. Install required Python packages
echo Installing required Python packages...
pip install flask openai==1.59.1 python-dotenv tenacity sendgrid
if %errorlevel% neq 0 (
    echo Failed to install required Python packages.
    exit /b 1
) else (
    echo Python packages installed successfully.
)

REM 8. Run the Python script app.py
if exist app.py (
    python app.py
    echo Running app.py...
) else (
    echo app.py not found in the current directory.
    exit /b 1
)
