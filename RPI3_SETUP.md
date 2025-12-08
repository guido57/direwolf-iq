# Running `soapysdr_to_direwolf` on Raspberry Pi 3 (Raspberry Pi OS)

Use this as a clean-install checklist for a Pi 3 (Model B/B+). It assumes Raspberry Pi OS Lite (64-bit preferred). Commands run as the `pi` user unless noted.

## 1) Base OS prep
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git build-essential cmake pkg-config \
    python3 python3-pip python3-numpy python3-soapysdr \
    csdr direwolf

# Optional: nicer monitoring tools
sudo apt install -y htop
```

## 2) SoapySDR device support (pick what you own)

### RTL-SDR
```bash
sudo apt install -y rtl-sdr soapysdr-module-rtlsdr
# USB access
sudo usermod -a -G plugdev,dialout $USER
```

### SDRplay RSP1 / RSP1B
```bash
cd /tmp
wget https://www.sdrplay.com/software/SDRplay_RSP_API-Linux-3.15.1.run
chmod +x SDRplay_RSP_API-Linux-3.15.1.run
sudo ./SDRplay_RSP_API-Linux-3.15.1.run
sudo apt install -y soapysdr-module-sdrplay
```

> If you use another SDR (Airspy, HackRF, etc.), install its Soapy module similarly (e.g., `sudo apt install soapysdr-module-airspy`).

### Verify SoapySDR sees your SDR
```bash
SoapySDRUtil --find
```

## 3) Clone the project and select the branch
```bash
cd ~
git clone https://github.com/guido57/direwolf-iq.git
cd direwolf-iq
git checkout soapysdr_to_direwolf
```

## 4) Quick smoke test (list devices)
```bash
cd scripts
python3 soapysdr_to_direwolf.py --list-devices
```

## 5) Run a basic stream test

### RTL-SDR (use 250 kHz for best Pi stability)
```bash
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 250000 --gain 49.6
```

### SDRplay RSP1/RSP1B (auto gain)
```bash
python3 soapysdr_to_direwolf.py --device sdrplay --freq 144.8 --rate 250000
```

You should see IQ samples emitted (CF32). Ctrl+C to stop.

## 6) Feed direwolf (CLI path)
```bash
python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --rate 250000 --gain 49.6 | \
  csdr fir_decimate_cc 8 | \
  direwolf -M -t 0 -r 31250 -n 1 iq:31250
```

Adjust the decimation rate and `iq:` rate to match your chosen sample rate.

## 7) Config-file workflow (recommended)
```bash
cp rtlsdr.conf rtlsdr_pi3.conf
nano rtlsdr_pi3.conf   # set frequency, sample rate, gain
python3 soapysdr_to_direwolf.py --config rtlsdr_pi3.conf --launcher
```

## 8) Optional web UI
```bash
pip3 install --user flask flask-socketio python-socketio eventlet
python3 soapysdr_to_direwolf.py --config rtlsdr_pi3.conf --launcher --web
# Browse to http://<pi-ip>:5000
```

## 9) Autostart (systemd)
Create `/etc/systemd/system/soapysdr-direwolf.service`:
```ini
[Unit]
Description=SoapySDR to Direwolf IQ Streaming
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/direwolf-iq/scripts
ExecStart=/usr/bin/python3 /home/pi/direwolf-iq/scripts/soapysdr_to_direwolf.py --config /home/pi/direwolf-iq/scripts/rtlsdr_pi3.conf --launcher
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable soapysdr-direwolf
sudo systemctl start soapysdr-direwolf
sudo systemctl status soapysdr-direwolf
```

## 10) Pi 3 performance tips
- Preferred sample rate for RTL-SDR: **250 kHz** (minimizes USB jitter). For RSP1/RSP1B you can use 250 kHz–1.024 MHz; 2.048 MHz is usable but shows higher variance.
- Use wired Ethernet on Pi 3 for stability (USB and Wi‑Fi share bus).
- Keep CPU load in check: `htop`; disable HDMI if headless: `/opt/vc/bin/tvservice -o`.
- Ensure solid 5V/3A power; undervoltage causes USB flakiness.

## 11) Troubleshooting quick hits
- **No devices found**: `SoapySDRUtil --find`; ensure the matching Soapy module is installed.
- **USB permission denied**: add user to `plugdev`/`dialout`, re-login.
- **Dropped samples**: lower `--rate` (try 192000 or 96000), avoid Wi‑Fi transfers during tests.
- **Web UI not reachable**: confirm Flask deps installed; try IP instead of hostname.

## Done
At this point streaming to direwolf should work. Start with the config-file launcher, then add the web UI or systemd service as needed.