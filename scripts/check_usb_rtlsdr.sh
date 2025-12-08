#!/bin/bash
# Check USB and RTL-SDR related settings that might affect performance

echo "=========================================="
echo "USB Controller Information"
echo "=========================================="
lsusb -t 2>/dev/null || echo "lsusb not available"
echo ""

echo "=========================================="
echo "RTL-SDR USB Device Details"
echo "=========================================="
lsusb -v -d 0bda:2838 2>/dev/null | grep -E "bcdUSB|MaxPower|bInterval|wMaxPacketSize" || echo "RTL-SDR not found"
echo ""

echo "=========================================="
echo "USB Buffer Settings"
echo "=========================================="
cat /sys/module/usbcore/parameters/usbfs_memory_mb 2>/dev/null || echo "Setting not available"
echo ""

echo "=========================================="
echo "RTL-SDR Kernel Module"
echo "=========================================="
lsmod | grep -E "rtl|dvb" || echo "No RTL modules loaded"
echo ""

echo "=========================================="
echo "USB Errors/Stats"
echo "=========================================="
dmesg | tail -50 | grep -i "usb\|rtl" || echo "No recent USB/RTL messages"
echo ""

echo "=========================================="
echo "CPU Governor (affects performance)"
echo "=========================================="
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || echo "Not available"
echo ""

echo "=========================================="
echo "librtlsdr version and build info"
echo "=========================================="
rtl_test -h 2>&1 | head -5
echo ""

echo "=========================================="
echo "Check for USB bandwidth issues"
echo "=========================================="
cat /sys/kernel/debug/usb/devices 2>/dev/null | grep -A 10 "Vendor=0bda ProdID=2838" || echo "Debug info not accessible (need sudo)"
