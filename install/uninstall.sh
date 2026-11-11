#!/bin/bash

# Formatting stuff
bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)
green=$(tput setaf 2)

APPNAME="inkypi"
INSTALL_PATH="/usr/local/$APPNAME"
BINPATH="/usr/local/bin"
VENV_PATH="$INSTALL_PATH/venv_$APPNAME"
SERVICE_FILE="/etc/systemd/system/$APPNAME.service"
CONFIG_DIR="$INSTALL_PATH/src/config"

echo_success() {
  echo -e "$1 [\e[32m\xE2\x9C\x94\e[0m]"
}

echo_override() {
  echo -e "\r$1"
}

echo_header() {
  echo -e "${bold}$1${normal}"
}

echo_error() {
  echo -e "${red}$1${normal} [\e[31m\xE2\x9C\x98\e[0m]\n"
}

check_permissions() {
  # Ensure the script is run with sudo
  if [ "$EUID" -ne 0 ]; then
    echo_error "ERROR: Uninstallation requires root privileges. Please run it with sudo."
    exit 1
  fi
}

stop_service() {
  echo "Stopping $APPNAME service"
  if /usr/bin/systemctl is-active --quiet "$APPNAME.service"
  then
    /usr/bin/systemctl stop "$APPNAME.service"
    echo_success "\tService stopped successfully."
  else
    echo_success "\tService is not running."
  fi
}

disable_service() {
  echo "Disabling $APPNAME service"
  if [ -f "$SERVICE_FILE" ]; then
    /usr/bin/systemctl disable "$APPNAME.service"
    rm -f "$SERVICE_FILE"
    /usr/bin/systemctl daemon-reload
    echo_success "\tService disabled and removed."
  else
    echo_success "\tService file does not exist. Nothing to remove."
  fi
}

remove_files() {
  echo "Removing application files"
  # Remove device.json if it exists
  if [ -f "$CONFIG_DIR/device.json" ]; then
    rm "$CONFIG_DIR/device.json"
    echo_success "\tRemoved device.json."
  else
    echo_success "\tdevice.json does not exist in $CONFIG_DIR"
  fi

  # Remove plugins.json if it exists
  if [ -f "$CONFIG_DIR/plugins.json" ]; then
    rm "$CONFIG_DIR/plugins.json"
    echo_success "\tRemoved plugins.json."
  else
    echo_success "\tplugins.json does not exist in $CONFIG_DIR"
  fi

  # Remove the installation directory
  if [ -d "$INSTALL_PATH" ]; then
    rm -rf "$INSTALL_PATH"
    echo_success "\tInstallation directory $INSTALL_PATH removed."
  else
    echo_success "\tInstallation directory $INSTALL_PATH does not exist."
  fi

  # Remove the executable
  if [ -f "$BINPATH/$APPNAME" ]; then
    rm -f "$BINPATH/$APPNAME"
    echo_success "\tExecutable $BINPATH/$APPNAME removed."
  else
    echo_success "\tExecutable $BINPATH/$APPNAME does not exist."
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

check_permissions
confirm_uninstall
stop_service
disable_service
remove_files

echo_success "Uninstallation complete."
echo_header "All components of $APPNAME have been removed."
