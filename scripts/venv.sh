#!/usr/bin/env bash

VENV_DIR="${VENV_DIR:-.venv}"
REQUIREMENTS_FILE="install/requirements-dev.txt"
SRC_DIR="$(realpath src)"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv $VENV_DIR

    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Ensure python3 is installed."
        exit 1
    fi
fi

echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

if [ -z "$VIRTUAL_ENV" ]; then
    echo "Failed to activate virtual environment."
    exit 1
fi

python -m pip install --upgrade pip
python -m pip install --no-cache-dir -r $REQUIREMENTS_FILE

export PYTHONPATH="$PYTHONPATH:$SRC_DIR"
export SRC_DIR=$SRC_DIR

echo "Python virtual environment initialized, run 'deactivate' to exit"