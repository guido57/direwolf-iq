#!/bin/bash
# Check software versions on both systems

echo "=========================================="
echo "System Information"
echo "=========================================="
uname -a
echo ""

echo "=========================================="
echo "Python Version"
echo "=========================================="
python3 --version
echo ""

echo "=========================================="
echo "SoapySDR Version"
echo "=========================================="
python3 -c "import SoapySDR; print(SoapySDR.getAPIVersion())" 2>/dev/null || echo "Not available"
echo ""

echo "=========================================="
echo "RTL-SDR Library"
echo "=========================================="
ldconfig -p | grep rtlsdr || echo "Not found in ldconfig"
dpkg -l | grep rtl-sdr || echo "Package not found"
rtl_test -t 2>&1 | head -20 || echo "rtl_test not available"
echo ""

echo "=========================================="
echo "SoapySDR RTL Module"
echo "=========================================="
SoapySDRUtil --info 2>&1 | grep -A 5 "rtlsdr" || echo "Not found"
SoapySDRUtil --make="driver=rtlsdr" --info 2>&1 | head -30 || echo "Cannot query device"
echo ""

echo "=========================================="
echo "csdr Version and Details"
echo "=========================================="
which csdr
csdr 2>&1 | head -20 || echo "csdr not found"
file $(which csdr) || echo "csdr binary not found"
echo ""

echo "=========================================="
echo "NumPy Version (affects math operations)"
echo "=========================================="
python3 -c "import numpy; print(f'Version: {numpy.__version__}'); print(f'Config: {numpy.__config__.show()}')" 2>&1 | head -30
echo ""

echo "=========================================="
echo "CPU Info"
echo "=========================================="
lscpu | grep -E "Architecture|Model name|CPU MHz|BogoMIPS" || cat /proc/cpuinfo | grep -E "model name|cpu MHz|BogoMIPS" | head -5
echo ""

echo "=========================================="
echo "Temperature (if available)"
echo "=========================================="
vcgencmd measure_temp 2>/dev/null || sensors 2>/dev/null | grep -i temp || echo "Not available"
