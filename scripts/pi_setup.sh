#!/bin/bash
# Quick setup script for Direwolf Web Interface on Raspberry Pi
# Run with: bash scripts/pi_setup.sh

set -e  # Exit on error

echo "=========================================="
echo "Direwolf Web Interface - Pi Setup"
echo "=========================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Step 1: Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    cmake \
    build-essential \
    libasound2-dev \
    python3 \
    python3-pip \
    python3-numpy \
    csdr \
    libsoapysdr-dev \
    soapysdr-tools \
    python3-soapysdr

echo ""
echo "Step 1a: Installing SDRplay API (if using SDRplay RSP devices)..."
read -p "Do you have an SDRplay RSP device? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if ! systemctl is-active --quiet sdrplay 2>/dev/null; then
        echo "SDRplay API not detected. Please install it manually:"
        echo "  1. Download from: https://www.sdrplay.com/downloads/"
        echo "  2. Look for: SDRplay_RSP_API-ARM32-3.15.2.run (or latest version)"
        echo "  3. Run: sudo ./SDRplay_RSP_API-ARM32-3.15.2.run"
        echo "  4. Start service: sudo systemctl start sdrplay"
        echo "  5. Enable on boot: sudo systemctl enable sdrplay"
        echo ""
        read -p "Press Enter to continue setup without SDRplay API (you can install it later)..."
    else
        echo "SDRplay API service is running."
        sudo systemctl enable sdrplay
    fi
fi

echo ""
echo "Step 2: Installing Python dependencies..."
echo "Creating Python virtual environment..."
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-socketio
echo "Note: numpy and SoapySDR are installed system-wide via apt for better compatibility"
echo "To activate the virtual environment in the future, run: source venv/bin/activate"

echo ""
echo "Step 3: Building Direwolf..."
if [ ! -d "build" ]; then
    mkdir build
fi
cd build
cmake ..
make -j2  # Use 2 cores on Pi Zero 2 W
sudo make install

echo ""
echo "Step 4: Verifying installation..."
direwolf -v

echo ""
echo "Step 5: Checking for SDR devices..."
SoapySDRUtil --find || echo "No SDR devices found (this is OK if not connected yet)"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the web interface manually:"
echo "  cd $(pwd)/.."
echo "  source venv/bin/activate"
echo "  python3 scripts/web_interface.py"
echo ""
echo "Then access it at: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "IMPORTANT: If you're using an SDRplay RSP device, make sure:"
echo "  1. SDRplay API service is running: sudo systemctl status sdrplay"
echo "  2. Device is detected: SoapySDRUtil --find='driver=sdrplay'"
echo ""

read -p "Would you like to create a systemd service for auto-start? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_DIR=$(pwd)/..
    SERVICE_FILE=/etc/systemd/system/direwolf-web.service
    
    echo "Creating systemd service..."
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Direwolf Web Interface
After=network.target sdrplay.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/scripts/web_interface.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable direwolf-web.service
    
    read -p "Start the service now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl start direwolf-web.service
        echo ""
        echo "Service started! Checking status..."
        sleep 2
        sudo systemctl status direwolf-web.service --no-pager
        echo ""
        echo "Web interface should now be available at: http://$(hostname -I | awk '{print $1}'):5000"
    else
        echo ""
        echo "To start later, run: sudo systemctl start direwolf-web.service"
    fi
    
    echo ""
    echo "Useful commands:"
    echo "  sudo systemctl status direwolf-web.service  # Check status"
    echo "  sudo systemctl restart direwolf-web.service # Restart"
    echo "  sudo systemctl stop direwolf-web.service    # Stop"
    echo "  journalctl -u direwolf-web.service -f       # View live logs"
fi

echo ""
echo "Setup complete! See RASPBERRY_PI_SETUP.md for detailed documentation."
