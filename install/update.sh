#!/bin/bash

# Formatting stuff
bold=$(tput bold)
normal=$(tput sgr0)
green=$(tput setaf 2)
red=$(tput setaf 1)

SOURCE=${BASH_SOURCE[0]}
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE
done
SCRIPT_DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )

APPNAME="inkypi"
INSTALL_PATH="/usr/local/$APPNAME"
VENV_PATH="$INSTALL_PATH/venv_$APPNAME"

APT_REQUIREMENTS_FILE="$SCRIPT_DIR/debian-requirements.txt"
PIP_REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

echo_success() {
  echo -e "$1 [\e[32m\xE2\x9C\x94\e[0m]"
}

echo_error() {
  echo -e "$1 [\e[31m\xE2\x9C\x98\e[0m]\n"
}

# Ensure script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo_error "ERROR: This script requires root privileges. Please run it with sudo."
  exit 1
fi

apt-get update -y
if [ -f "$APT_REQUIREMENTS_FILE" ]; then
  echo "Installing system dependencies. "
  xargs -a "$APT_REQUIREMENTS_FILE" sudo apt-get install -y > /dev/null &
else
  echo_error "ERROR: System dependencies file $APT_REQUIREMENTS_FILE not found!"
  exit 1
fi

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
  echo_error "ERROR: Virtual environment not found at $VENV_PATH. Run the installation script first."
  exit 1
fi

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Install or update Python dependencies
if [ -f "$PIP_REQUIREMENTS_FILE" ]; then
  echo "Updating Python dependencies..."
  pip install --upgrade -r "$PIP_REQUIREMENTS_FILE" > /dev/null && echo_success "Dependencies updated successfully."
else
  echo_error "ERROR: Requirements file $PIP_REQUIREMENTS_FILE not found!"
  exit 1
fi

echo "Restarting $APPNAME service."
sudo systemctl restart $APPNAME.service

echo_success "Update completed."
