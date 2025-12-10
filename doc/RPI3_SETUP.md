# Raspberry Pi 3 Setup (RTL-SDR + SoapySDR + Direwolf IQ)

This guide captures the working steps to run the SoapySDR → csdr → Direwolf IQ pipeline on a Raspberry Pi 3 using an RTL-SDR dongle.

## 1) Kernel modules and permissions

- Blacklist kernel DVB drivers that auto-attach to RTL-SDR:

```bash
sudo tee /etc/modprobe.d/blacklist-rtlsdr.conf >/dev/null <<'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832_sdr
blacklist r820t
EOF
```

- Reboot, then confirm the device is not claimed by a kernel driver:

```bash
sudo reboot
# after reboot
lsusb | grep -i realtek
```

- udev/plugdev: ensure your user can access USB SDRs (typical on Raspberry Pi OS). If needed:

```bash
sudo usermod -aG plugdev $USER
newgrp plugdev
```

## 2) Packages

```bash
sudo apt update
sudo apt install \
  rtl-sdr librtlsdr0 librtlsdr-dev \
  soapysdr-tools libsoapysdr0.8 libsoapysdr-dev \
  soapysdr-module-rtlsdr soapysdr0.8-module-rtlsdr \
  csdr
```

Notes:
- ALSA/RtAudio errors during SoapySDR device scans are harmless.
- On some Raspberry Pi OS releases, the RTLSDR Soapy plugin file is named `librtlsdrSupport.so`.

Optional (to silence a SoapySDR warning about module name):
```bash
sudo ln -sf \
  /usr/lib/aarch64-linux-gnu/SoapySDR/modules0.8/librtlsdrSupport.so \
  /usr/lib/aarch64-linux-gnu/SoapySDR/modules0.8/libSoapyRTLSDRSupport.so
```

## 3) Verify hardware and Soapy core

```bash
SoapySDRUtil --find
SoapySDRUtil --probe="driver=rtlsdr"
rtl_test -t
```

You should see the device (driver `rtlsdr`, serial, tuner R820T) and the probe should list RX capabilities.

## 4) Python bindings (important)

Some Raspberry Pi images ship with very new Python versions (e.g., 3.13) while distro packages for `python3-soapysdr` may not include the compiled extension for that version. If `import SoapySDR` only shows `SoapySDR.py` without a matching `.so` extension, you have two options:

- Recommended: use a supported Python (e.g., 3.11) if available:

```bash
sudo apt install python3.11 python3.11-venv
python3.11 -c "import SoapySDR; print(SoapySDR.Device.enumerate())"
```

- Or build SoapySDR + Python bindings from source for your active Python:

```bash
# SoapySDR core
git clone https://github.com/pothosware/SoapySDR.git
cd SoapySDR && mkdir build && cd build
cmake .. -DPYTHON3_EXECUTABLE=$(which python3)
make -j$(nproc)
sudo make install
sudo ldconfig

# Python bindings
cd ../python
python3 setup.py build
sudo python3 setup.py install

# Soapy RTLSDR plugin
cd ~
git clone https://github.com/pothosware/SoapyRTLSDR.git
cd SoapyRTLSDR && mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig
```

Verification with Python:
```bash
python3 - <<'PY'
import SoapySDR
print('Bindings:', SoapySDR.__file__)
print('Devices:', [dict(d) for d in SoapySDR.Device.enumerate()])
# Try opening by driver
sdr = SoapySDR.Device({'driver':'rtlsdr'})
print('Opened:', sdr)
PY
```

## 5) Run the pipeline

Example `scripts/rtlsdr.conf` (already included):
```
DEVICE driver=rtlsdr serial=00000001
FREQUENCY 144.800
SAMPLE_RATE 250000
AGC false
GAIN TUNER 49.0
SETTING offset_tune false
```

Launch (adjust build path to your direwolf if needed):

```bash
cd scripts
python3 soapysdr_to_direwolf.py --config rtlsdr.conf \
  | csdr fir_decimate_cc 10 0.005 HAMMING \
  | ../build/src/direwolf -M -t 0 -r 25000 -n 1 iq:25000
```

If you use Python 3.11 specifically:
```bash
python3.11 soapysdr_to_direwolf.py --config rtlsdr.conf \
  | csdr fir_decimate_cc 10 0.005 HAMMING \
  | ../build/src/direwolf -M -t 0 -r 25000 -n 1 iq:25000
```

## 6) Troubleshooting quick facts

- "SoapySDR::Device::make() no match": the Python bindings cannot open the device — verify the Soapy RTLSDR module is found and that the Python C extension is installed for your Python version.
- Module load warning for `libSoapyRTLSDRSupport.so`: harmless if `librtlsdrSupport.so` exists; the symlink above can suppress the warning.
- ALSA/RtAudio errors during enumeration: ignorable for SDR use.
- If multiple RTL-SDRs: try `DEVICE driver=rtlsdr index=0` (or `serial=...`).
