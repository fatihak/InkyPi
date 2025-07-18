#!/bin/sh
set -e

# Copy the configuration
if [ ! -f src/config/device.json ]; then
    cp install/config_base/device.json src/config/
    sed -i 's/"mock": false/"mock": true/' src/config/device.json
fi

pip install --upgrade pip
pip3 install --no-cache-dir -r install/requirements.txt
pip3 install --no-cache-dir -r install/requirements-dev.txt