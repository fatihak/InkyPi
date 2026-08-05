#!/bin/bash

# =============================================================================
# Script Name: install-pi-weather-display.sh
# Description: Installs the standalone pi_weather_display renderer - a
#              lightweight, single-purpose alternative to the full InkyPi app
#              (no Flask, no Chromium, no plugins/playlist) intended for
#              weaker hardware like a Pi Zero W. Renders natively with Pillow
#              and runs periodically via a systemd timer instead of a
#              long-running service.
#
# Usage: sudo bash install-pi-weather-display.sh
# =============================================================================

set -e

bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)

SOURCE=${BASH_SOURCE[0]}
while [ -h "$SOURCE" ]; do
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE
done
SCRIPT_DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
REPO_DIR="$SCRIPT_DIR/.."
APP_SRC="$REPO_DIR/pi_weather_display"

APPNAME="pi-weather-display"
INSTALL_PATH="/usr/local/$APPNAME"
VENV_PATH="$INSTALL_PATH/venv"

APT_REQUIREMENTS_FILE="$SCRIPT_DIR/pi-weather-display-debian-requirements.txt"
PIP_REQUIREMENTS_FILE="$SCRIPT_DIR/pi-weather-display-requirements.txt"

SERVICE_FILE_SOURCE="$SCRIPT_DIR/$APPNAME.service"
SERVICE_FILE_TARGET="/etc/systemd/system/$APPNAME.service"
TIMER_FILE_SOURCE="$SCRIPT_DIR/$APPNAME.timer"
TIMER_FILE_TARGET="/etc/systemd/system/$APPNAME.timer"

echo_success() {
  echo -e "$1 [\e[32m\xE2\x9C\x94\e[0m]"
}

echo_error() {
  echo -e "${red}$1${normal} [\e[31m\xE2\x9C\x98\e[0m]\n"
}

echo_header() {
  echo -e "${bold}$1${normal}"
}

check_permissions() {
  if [ "$EUID" -ne 0 ]; then
    echo_error "ERROR: Installation requires root privileges. Please run it with sudo."
    exit 1
  fi
}

install_debian_dependencies() {
  echo "Installing system dependencies."
  if [ ! -f "$APT_REQUIREMENTS_FILE" ]; then
    echo_error "ERROR: System dependencies file $APT_REQUIREMENTS_FILE not found!"
    exit 1
  fi
  apt-get update > /dev/null
  xargs -a "$APT_REQUIREMENTS_FILE" apt-get install -y > /dev/null
  echo_success "\tSystem dependencies installed."
}

enable_interfaces() {
  echo "Enabling SPI interface (required for the Inky display)."
  sed -i 's/^dtparam=spi=.*/dtparam=spi=on/' /boot/firmware/config.txt
  sed -i 's/^#dtparam=spi=.*/dtparam=spi=on/' /boot/firmware/config.txt
  raspi-config nonint do_spi 0
  echo_success "\tSPI interface enabled."
}

create_venv() {
  echo "Creating python virtual environment at $VENV_PATH."
  python3 -m venv "$VENV_PATH"
  "$VENV_PATH/bin/python" -m pip install --upgrade pip -qq
  if [ ! -f "$PIP_REQUIREMENTS_FILE" ]; then
    echo_error "ERROR: Requirements file $PIP_REQUIREMENTS_FILE not found!"
    exit 1
  fi
  "$VENV_PATH/bin/python" -m pip install -r "$PIP_REQUIREMENTS_FILE" -qq
  echo_success "\tPython dependencies installed."
}

install_app() {
  echo "Linking $APP_SRC to $INSTALL_PATH/app"
  mkdir -p "$INSTALL_PATH"
  ln -sfn "$APP_SRC" "$INSTALL_PATH/app"
  echo_success "\tApp linked."
}

install_service() {
  echo "Installing $APPNAME systemd service and timer."
  if [ ! -f "$SERVICE_FILE_SOURCE" ] || [ ! -f "$TIMER_FILE_SOURCE" ]; then
    echo_error "ERROR: Service/timer files not found in $SCRIPT_DIR!"
    exit 1
  fi
  cp "$SERVICE_FILE_SOURCE" "$SERVICE_FILE_TARGET"
  cp "$TIMER_FILE_SOURCE" "$TIMER_FILE_TARGET"
  systemctl daemon-reload
  systemctl enable --now "$APPNAME.timer"
  echo_success "\tService and timer installed, timer started."
}

check_permissions
install_debian_dependencies
enable_interfaces
create_venv
install_app
install_service

echo_header "$(echo_success "Pi Weather Display installation complete!")"
echo_header "[-] Edit $APP_SRC/config.py to set your location before the next refresh."
echo_header "[-] A reboot may be required for the SPI interface change to take effect."
echo_header "[-] Check status with: systemctl status $APPNAME.timer"
echo_header "[-] View logs with: journalctl -u $APPNAME.service"
echo_header "[-] Force an immediate render with: systemctl start $APPNAME.service"
