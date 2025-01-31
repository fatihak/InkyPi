#!/bin/bash

# Formatting stuff
bold=$(tput bold)
normal=$(tput sgr0)
red=$(tput setaf 1)
green=$(tput setaf 2)

SOURCE=${BASH_SOURCE[0]}
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE
done
SCRIPT_DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )

APPNAME="inkypi"
INSTALL_PATH="/usr/local/$APPNAME"
SRC_PATH="$SCRIPT_DIR/../src"
BINPATH="/usr/local/bin"
VENV_PATH="$INSTALL_PATH/venv_$APPNAME"

SERVICE_FILE="$APPNAME.service"
SERVICE_FILE_SOURCE="$SCRIPT_DIR/$SERVICE_FILE"
SERVICE_FILE_TARGET="/etc/systemd/system/$SERVICE_FILE"

APT_REQUIREMENTS_FILE="$SCRIPT_DIR/debian-requirements.txt"
PIP_REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"


check_permissions() {
  # Ensure the script is run with sudo
  if [ "$EUID" -ne 0 ]; then
    echo_error "ERROR: Installation requires root privileges. Please run it with sudo."
    exit 1
  fi
}

enable_interfaces(){
  echo "Enabling interfaces required for $APPNAME"
  #enable spi
  sudo sed -i 's/^dtparam=spi=.*/dtparam=spi=on/' /boot/config.txt
  sudo sed -i 's/^#dtparam=spi=.*/dtparam=spi=on/' /boot/config.txt
  sudo raspi-config nonint do_spi 0
  echo_success "\tSPI Interface has been enabled."
  #enable i2c
  sudo sed -i 's/^dtparam=i2c_arm=.*/dtparam=i2c_arm=on/' /boot/config.txt
  sudo sed -i 's/^#dtparam=i2c_arm=.*/dtparam=i2c_arm=on/' /boot/config.txt
  sudo raspi-config nonint do_i2c 0
  echo_success "\tI2C Interface has been enabled."
  sed -i '/^dtparam=spi=on/a dtoverlay=spi0-0cs' /boot/firmware/config.txt
}

show_loader() {
  local pid=$!
  local delay=0.1
  local spinstr='|/-\'
  printf "$1 [${spinstr:0:1}] "
  while ps a | awk '{print $1}' | grep -q "${pid}"; do
    local temp=${spinstr#?}
    printf "\r$1 [${temp:0:1}] "
    spinstr=${temp}${spinstr%"${temp}"}
    sleep ${delay}
  done
  if [[ $? -eq 0 ]]; then
    printf "\r$1 [\e[32m\xE2\x9C\x94\e[0m]\n"
  else
    printf "\r$1 [\e[31m\xE2\x9C\x98\e[0m]\n"
  fi
}

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

echo_blue() {
  echo -e "\e[38;2;65;105;225m$1\e[0m"
}


install_debian_dependencies() {
  if [ -f "$APT_REQUIREMENTS_FILE" ]; then
    xargs -a "$APT_REQUIREMENTS_FILE" sudo apt-get install -y > /dev/null &
    show_loader "Installing system dependencies. "
  else
    echo "ERROR: System dependencies file $APT_REQUIREMENTS_FILE not found!"
    exit 1
  fi
}

create_venv(){
  echo "Creating python virtual environment. "
  python3 -m venv "$VENV_PATH"
  $VENV_PATH/bin/python -m pip install -r $PIP_REQUIREMENTS_FILE > /dev/null &
  show_loader "\tInstalling python dependencies. "
}

install_app_service() {
  echo "Installing $APPNAME systemd service."
  if [ -f "$SERVICE_FILE_SOURCE" ]; then
    cp "$SERVICE_FILE_SOURCE" "$SERVICE_FILE_TARGET"
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_FILE
  else
    echo_error "ERROR: Service file $SERVICE_FILE_SOURCE not found!"
    exit 1
  fi
}

install_executable() {
  echo "Adding executable to ${BINPATH}/$APPNAME"
  cp $SCRIPT_DIR/inkypi $BINPATH/
  sudo chmod +x $BINPATH/$APPNAME
}

install_config() {
  CONFIG_BASE_DIR="$SCRIPT_DIR/config_base"
  CONFIG_DIR="$SRC_PATH/config"
  echo "Copying config files to $CONFIG_DIR"

  # Check and copy device.config if it doesn't exist
  if [ ! -f "$CONFIG_DIR/device.json" ]; then
    cp "$CONFIG_BASE_DIR/device.json" "$CONFIG_DIR/"
    show_loader "\tCopying device.config to $CONFIG_DIR"
  else
    echo_success "\tdevice.json already exists in $CONFIG_DIR"
  fi
}

stop_service() {
    echo "Checking if $SERVICE_FILE is running"
    if /usr/bin/systemctl is-active --quiet $SERVICE_FILE
    then
      /usr/bin/systemctl stop $SERVICE_FILE > /dev/null &
      show_loader "Stopping $APPNAME service"
    else  
      echo_success "\t$SERVICE_FILE not running"
    fi
}

start_service() {
  echo "Starting $APPNAME service."
  sudo systemctl start $SERVICE_FILE
}

copy_project() {
  # Check if an existing installation is present
  echo "Installing $APPNAME to $INSTALL_PATH"
  if [[ -d $INSTALL_PATH ]]; then
    rm -rf "$INSTALL_PATH" > /dev/null
    show_loader "\tRemoving existing installation found at $INSTALL_PATH"
  fi

  mkdir -p "$INSTALL_PATH"

  ln -sf "$SRC_PATH" "$INSTALL_PATH/src"
  show_loader "\tCreating symlink from $SRC_PATH to $INSTALL_PATH/src"
}

# Get Raspberry Pi hostname
get_hostname() {
  echo "$(hostname)"
}

# Get Raspberry Pi IP address
get_ip_address() {
  ip_address=$(hostname -I | awk '{print $1}')
  echo "$ip_address"
}

ask_for_reboot() {
  # Get hostname and IP address
  hostname=$(get_hostname)
  ip_address=$(get_ip_address)
  echo_header "$(echo_success "${APPNAME^^} Installation Complete!")"
  echo_header "[•] A reboot of your Raspberry Pi is required for the changes to take effect"
  echo_header "[•] After your Pi is rebooted, you can access the web UI by going to $(echo_blue "'$hostname.local'") or $(echo_blue "'$ip_address'") in your browser."
  echo_header "[•] If you encounter any issues or have suggestions, please submit them here: https://github.com/fatihak/InkyPi/issues"

  read -p "Would you like to restart your Raspberry Pi now? [Y/N] " userInput
  userInput="${userInput^^}"

  if [[ "${userInput,,}" == "y" ]]; then
    echo_success "You entered 'Y', rebooting now..."
    sleep 2
    sudo reboot now
  elif [[ "${userInput,,}" == "n" ]]; then
    echo "Please restart your Raspberry Pi later to apply changes by running 'sudo reboot now'."
    exit
  else
    echo "Unknown input, please restart your Raspberry Pi later to apply changes by running 'sudo reboot now'."
    sleep 1
  fi
}


check_permissions
stop_service
enable_interfaces
install_debian_dependencies
copy_project
create_venv
install_executable
install_config
install_app_service
ask_for_reboot
