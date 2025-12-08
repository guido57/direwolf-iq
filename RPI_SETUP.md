# Running soapysdr_to_direwolf on Raspberry Pi Zero 2 W

This guide covers setup and testing of the SoapySDR-based SDR streaming on Raspberry Pi Zero 2 W.

## Hardware Requirements

- **Raspberry Pi Zero 2 W** (or Pi 3/4+)
- **SDR Device** (one of):
  - RTL-SDR (RTL2832U dongle)
  - SDRplay RSP1/RSP1B
  - Airspy R2/Mini
  - HackRF One
- **USB Hub** (recommended for Pi Zero 2 W - has limited USB power)
- **microSD Card** with at least 4GB space
- **USB-C Power Supply** (5V/3A minimum for stable operation)

## Initial Setup

### 1. Install OS and Update

```bash
# Use Raspberry Pi Imager to flash Raspberry Pi OS Lite (latest)
# SSH into the Pi
ssh pi@raspberrypi.local

# Update system
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake git pkg-config
```

### 2. Install SoapySDR Core

```bash
# Install SoapySDR from repositories (faster than building from source)
sudo apt install -y python3-soapysdr python3-numpy

# Verify installation
SoapySDRUtil --info
```

### 3. Install SDR Device Support

Choose **one** or more based on your hardware:

#### RTL-SDR
```bash
sudo apt install -y rtl-sdr
sudo apt install -y soapysdr-module-rtlsdr

# Add user to dialout group for USB access
sudo usermod -a -G dialout $USER
```

#### SDRplay RSP1/RSP1B
```bash
# Download and install SDRplay API
cd /tmp
wget https://www.sdrplay.com/software/SDRplay_RSP_API-Linux-3.15.1.run
chmod +x SDRplay_RSP_API-Linux-3.15.1.run
sudo ./SDRplay_RSP_API-Linux-3.15.1.run

# Install SoapySDR wrapper
sudo apt install -y soapysdr-module-sdrplay
```

#### Airspy
```bash
sudo apt install -y airspy
sudo apt install -y soapysdr-module-airspy
```

#### HackRF
```bash
sudo apt install -y hackrf
sudo apt install -y soapysdr-module-hackrf
```

### 4. Install Additional Dependencies

```bash
# For csdr (decimation)
sudo apt install -y csdr

# For direwolf
sudo apt install -y direwolf

# Optional: For web interface
pip3 install flask flask-socketio python-socketio
```

### 5. Clone or Copy Project

```bash
# Option A: Clone from GitHub
git clone https://github.com/guido57/direwolf-iq.git
cd direwolf-iq

# Option B: Copy from your main machine via SCP
scp -r ~/Documents/PlatformIO/Projects/direwolf-iq pi@raspberrypi.local:~/
```

## Testing

### Step 1: List Available Devices

```bash
cd direwolf-iq/scripts
python3 soapysdr_to_direwolf.py --list-devices
```

Example output:
```
Available SoapySDR devices:
Device 0: RTL-SDR (rtlsdr)
Device 1: SDRplay RSP1 (sdrplay)
```

### Step 2: Test Direct Streaming

Test with your device (replace `rtlsdr` or `sdrplay` as needed):

```bash
# RTL-SDR test
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 192000 --gain 40

# SDRplay RSP1 test
python3 soapysdr_to_direwolf.py --device sdrplay --freq 144.8 --rate 192000 --ifgr 23 --rfgr 0
```

You should see CF32 IQ data streaming to stdout. Press Ctrl+C to stop.

### Step 3: Test with Decimation

```bash
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 192000 --gain 40 | \
  csdr fir_decimate_cc 8 | xxd | head -20
```

This pipes the IQ stream through csdr for 8x decimation and displays the hex output.

### Step 4: Test with direwolf

```bash
# Direct streaming to direwolf
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 192000 --gain 40 | \
  csdr fir_decimate_cc 8 | \
  direwolf -M -t 0 -r 24000 -n 1 iq:24000
```

### Step 5: Test CLI Launcher Mode

```bash
# Copy config file
cp rtlsdr.conf rtlsdr_pi.conf

# Edit for your setup
nano rtlsdr_pi.conf

# Run launcher
python3 soapysdr_to_direwolf.py --config rtlsdr_pi.conf --launcher
```

### Step 6: Test Web Interface (Optional)

```bash
# Start web interface
python3 soapysdr_to_direwolf.py --config rtlsdr_pi.conf --launcher --web

# Access from another machine on your network
# http://raspberrypi.local:5000
```

## Performance Tuning for Pi Zero 2 W

The Pi Zero 2 W has 512MB RAM and less CPU than Pi 3/4. Here are optimization tips:

### 1. Reduce Sample Rate
```bash
# Instead of 192000, use lower rates
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 96000 --gain 40
```

### 2. Use Configuration File
Create `rtlsdr_optimized.conf`:
```
DEVICE=rtlsdr
FREQUENCY=144800000
SAMPLE_RATE=96000
GAIN=40
```

Run with:
```bash
python3 soapysdr_to_direwolf.py --config rtlsdr_optimized.conf --launcher
```

### 3. Disable Web Interface on Zero 2 W
The web interface adds overhead. Stick with CLI launcher:
```bash
python3 soapysdr_to_direwolf.py --config rtlsdr_pi.conf --launcher
```

### 4. Monitor Resources
```bash
# Check memory usage
free -h

# Check CPU load
top -b -n 1 | head -10

# Check temperature
vcgencmd measure_temp
```

### 5. Power Management
```bash
# Disable HDMI (saves ~30mA)
/opt/vc/bin/tvservice -o

# Reduce GPU memory (if not using display)
# Edit /boot/config.txt and set:
# gpu_mem=16
```

## Troubleshooting

### Issue: "No SoapySDR devices found"
```bash
# Check available modules
ls /usr/lib/arm-linux-gnueabihf/SoapySDR/modules*/

# If empty, install device support:
sudo apt install soapysdr-module-rtlsdr  # or other device
```

### Issue: USB Permission Denied
```bash
# Add user to plugdev group
sudo usermod -a -G plugdev $USER

# Log out and log back in, or:
newgrp plugdev
```

### Issue: Slow Performance / Dropped Samples
```bash
# Reduce sample rate
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 96000

# Check CPU load with htop
sudo apt install htop
htop
```

### Issue: Web Interface Won't Connect
```bash
# Check if Flask is installed
pip3 list | grep -i flask

# If not installed:
pip3 install flask flask-socketio

# Access via IP address instead of hostname:
# http://192.168.x.x:5000
```

## Remote Operation

Run on Pi, display on your main machine:

### Option 1: SSH Tunnel for Web Interface
```bash
# On your main machine
ssh -L 5000:localhost:5000 pi@raspberrypi.local

# Then open browser to http://localhost:5000
```

### Option 2: Pipe to Network direwolf Instance
```bash
# On Pi (streaming only)
python3 soapysdr_to_direwolf.py --config rtlsdr_pi.conf | nc -u main-machine.local 4000

# On main machine (receive and decode)
nc -u -l 4000 | direwolf -M -t 0 -r 24000 -n 1 iq:24000
```

## Systemd Service (Optional)

Create `/etc/systemd/system/soapysdr-direwolf.service`:

```ini
[Unit]
Description=SoapySDR to Direwolf IQ Streaming
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/direwolf-iq/scripts
ExecStart=/usr/bin/python3 /home/pi/direwolf-iq/scripts/soapysdr_to_direwolf.py --config rtlsdr_pi.conf --launcher
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then run:
```bash
sudo systemctl daemon-reload
sudo systemctl enable soapysdr-direwolf
sudo systemctl start soapysdr-direwolf
sudo systemctl status soapysdr-direwolf
```

## Next Steps

1. Start with Step 2 (list devices) to confirm hardware detection
2. Progress through Steps 3-4 to verify data streaming
3. Move to Step 5 (CLI launcher) for production use
4. Consider Step 6 (web interface) for remote monitoring

Good luck with your Raspberry Pi Zero 2 W setup!
