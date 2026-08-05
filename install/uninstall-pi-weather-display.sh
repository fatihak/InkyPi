#!/bin/bash

# Uninstalls the standalone pi_weather_display renderer (systemd service,
# timer, venv). Does not touch the git checkout itself.

bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)

APPNAME="pi-weather-display"
INSTALL_PATH="/usr/local/$APPNAME"
SERVICE_FILE="/etc/systemd/system/$APPNAME.service"
TIMER_FILE="/etc/systemd/system/$APPNAME.timer"

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
    echo_error "ERROR: Uninstallation requires root privileges. Please run it with sudo."
    exit 1
  fi
}

confirm_uninstall() {
  echo -e "${bold}Are you sure you want to uninstall $APPNAME? (y/N): ${normal}"
  read -r confirmation
  if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
    echo_error "Uninstallation cancelled."
    exit 1
  fi
}

disable_timer() {
  echo "Disabling $APPNAME timer and service."
  systemctl disable --now "$APPNAME.timer" 2>/dev/null || true
  rm -f "$SERVICE_FILE" "$TIMER_FILE"
  systemctl daemon-reload
  echo_success "\tTimer and service removed."
}

remove_files() {
  echo "Removing installation directory."
  if [ -d "$INSTALL_PATH" ]; then
    rm -rf "$INSTALL_PATH"
    echo_success "\tRemoved $INSTALL_PATH (app symlink + venv)."
  else
    echo_success "\t$INSTALL_PATH does not exist."
  fi
}

check_permissions
confirm_uninstall
disable_timer
remove_files

echo_success "Uninstallation complete."
echo_header "The git checkout and pi_weather_display/ source are untouched."
