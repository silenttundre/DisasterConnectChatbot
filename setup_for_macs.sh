#!/bin/bash
# 3. Create a Python virtual environment called dcVenv if it doesn't exist
VENV="dcVenv"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    echo "Virtual environment 'dcVenv' created."
else
    echo "Virtual environment 'dcVenv' already exists."
fi

# 4. Activate the dcVenv virtual environment
source "$VENV/bin/activate"
if [ $? -ne 0 ]; then
    echo "Failed to activate the virtual environment 'dcVenv'."
    exit 1
else
    echo "Activated virtual environment 'dcVenv'."
fi

# 5. Install required Python packages
echo "Installing required Python packages..."
pip install flask openai==1.59.9 python-dotenv tenacity sendgrid
if [ $? -ne 0 ]; then
    echo "Failed to install required Python packages."
    exit 1
else
    echo "Python packages installed successfully."
fi

# 8. Run the Python script app.py
if [ -f app.py ]; then
    python3 app.py
    echo "Running app.py..."
else
    echo "app.py not found in the current directory."
    exit 1
fi
