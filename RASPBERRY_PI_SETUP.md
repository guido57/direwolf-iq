# Raspberry Pi Setup Guide

This guide will help you set up direwolf with the web interface on a Raspberry Pi Zero 2 W.

## Prerequisites

- Raspberry Pi Zero 2 W with Raspberry Pi OS installed
- Internet connection
- SDRplay RSP1 or compatible SDR connected via USB

## Installation Steps

### 1. Clone the Repository

```bash
cd ~
git clone -b web_interface https://github.com/guido57/direwolf-iq.git
cd direwolf-iq
```

### 2. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    git \
    cmake \
    build-essential \
    libasound2-dev \
    python3 \
    python3-pip \
    csdr \
    libsoapysdr-dev \
    soapysdr-tools
```

### 3. Install SDRplay Support (if using SDRplay RSP1)

```bash
# Download and install SDRplay API
wget https://www.sdrplay.com/software/SDRplay_RSP_API-Linux-3.15.2.run
chmod +x SDRplay_RSP_API-Linux-3.15.2.run
sudo ./SDRplay_RSP_API-Linux-3.15.2.run

# Install SoapySDR plugin for SDRplay
sudo apt-get install -y soapysdr-module-sdrplay3
```

### 4. Install Python Dependencies

```bash
pip3 install flask flask-socketio numpy SoapySDR
```

### 5. Build Direwolf

```bash
cd ~/direwolf-iq
mkdir -p build
cd build
cmake ..
make -j2  # Use 2 cores on Pi Zero 2 W
sudo make install
```

### 6. Verify Installation

```bash
# Check direwolf installation
direwolf -v

# Check if SDR is detected
SoapySDRUtil --find

# Test with a sample file
cd ~/direwolf-iq/test/iq
cat iq48k_cfloat.raw | direwolf -M -t 0 -r 48000 -n 1 iq:48000 2>&1 | head -20
```

## Running the Web Interface

### Manual Start

```bash
cd ~/direwolf-iq
python3 scripts/web_interface.py
```

Then open a web browser and navigate to:
- From Pi: `http://localhost:5000`
- From another device on LAN: `http://[PI_IP_ADDRESS]:5000`

### Auto-start on Boot (Optional)

Create a systemd service:

```bash
sudo nano /etc/systemd/system/direwolf-web.service
```

Paste this content (adjust paths if needed):

```ini
[Unit]
Description=Direwolf Web Interface
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/direwolf-iq
ExecStart=/usr/bin/python3 /home/pi/direwolf-iq/scripts/web_interface.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable direwolf-web.service
sudo systemctl start direwolf-web.service

# Check status
sudo systemctl status direwolf-web.service
```

## Configuration

Edit the default configuration in `scripts/web_interface.py` or use the web UI:

- **Frequency**: 144.8 MHz (default for APRS in Europe)
- **IF Gain**: 23 (optimal for SDRplay RSP1)
- **RF Gain**: 0
- **AGC**: Enable for automatic gain control

## Troubleshooting

### SDR Not Detected

```bash
# Check USB devices
lsusb

# Check SoapySDR detection
SoapySDRUtil --probe="driver=sdrplay"
```

### Permission Issues with SDR

```bash
# Add user to plugdev group
sudo usermod -a -G plugdev $USER

# Create udev rule for SDRplay
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1df7", MODE="0666"' | sudo tee /etc/udev/rules.d/66-sdrplay.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Web Interface Not Accessible from LAN

Check firewall settings:
```bash
sudo ufw allow 5000/tcp
```

### Low Performance / High CPU Usage

The Pi Zero 2 W has limited CPU power. Consider:
- Reducing the sample rate
- Disabling AGC if not needed
- Using a simpler decimation filter
- Monitoring with: `top` or `htop`

## Performance Tips for Pi Zero 2 W

1. **Disable GUI** (if running headless):
   ```bash
   sudo systemctl set-default multi-user.target
   sudo reboot
   ```

2. **Overclock** (optional, may require better cooling):
   Edit `/boot/config.txt`:
   ```
   over_voltage=2
   arm_freq=1200
   ```

3. **Monitor temperature**:
   ```bash
   vcgencmd measure_temp
   ```

## Updating

To update to the latest version:

```bash
cd ~/direwolf-iq
git pull origin web_interface
cd build
make clean
make -j2
sudo make install
```

## Support

For issues specific to:
- **Direwolf IQ input**: Check `PULL_REQUEST.md` in the repository
- **Web interface**: Check `scripts/web_interface.py`
- **SDRplay**: Visit https://www.sdrplay.com/support/

## Useful Commands

```bash
# View live logs
journalctl -u direwolf-web.service -f

# Restart service
sudo systemctl restart direwolf-web.service

# Stop service
sudo systemctl stop direwolf-web.service

# Check system resources
htop
```
