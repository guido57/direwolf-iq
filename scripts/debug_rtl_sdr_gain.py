#!/usr/bin/env python3
"""
Debug: Compare rtl_sdr and SoapySDR gain application and power scaling
"""

import subprocess
import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import time

def measure_with_rtl_sdr(sample_rate=250000, gain=49.6):
    """Measure with rtl_sdr - raw uint8"""
    cmd = [
        'rtl_sdr',
        '-f', '144800000',
        '-s', str(sample_rate),
        '-g', str(gain),
        '-n', str(int(sample_rate * 1)),
        '-'
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    chunk = process.stdout.read(sample_rate * 2)  # 1 second of uint8 pairs
    process.wait()
    
    uint8_data = np.frombuffer(chunk, dtype=np.uint8)
    float_data = (uint8_data.astype(np.float32) - 127.5) / 127.5
    iq_complex = float_data[0::2] + 1j * float_data[1::2]
    
    power = np.mean(np.abs(iq_complex)**2)
    power_dbfs = 10 * np.log10(power) if power > 0 else -200
    
    return power_dbfs, power

def measure_with_soapysdr(sample_rate=250000, gain=49.6):
    """Measure with SoapySDR - CF32"""
    sdr = SoapySDR.Device({'driver': 'rtlsdr'})
    sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
    sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    sdr.setGain(SOAPY_SDR_RX, 0, gain)
    
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
    
    buff = np.zeros(4096, dtype=np.complex64)
    for _ in range(10):
        sdr.readStream(rx_stream, [buff], len(buff))
    
    time.sleep(0.2)
    
    powers = []
    for _ in range(10):
        sr = sdr.readStream(rx_stream, [buff], len(buff))
        if sr.ret > 0:
            samples = buff[:sr.ret]
            power = np.mean(np.abs(samples)**2)
            power_dbfs = 10 * np.log10(power) if power > 0 else -200
            powers.append(power_dbfs)
    
    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    del sdr
    
    avg_power_dbfs = np.mean(powers) if powers else -200
    avg_power_linear = 10 ** (avg_power_dbfs / 10)
    
    return avg_power_dbfs, avg_power_linear

print("="*70)
print("Debug: rtl_sdr vs SoapySDR Power Measurement")
print("="*70)

for sample_rate in [250000, 1024000]:
    print(f"\n{'='*70}")
    print(f"Sample Rate: {sample_rate} Hz")
    print(f"{'='*70}")
    
    print("\nMeasuring with rtl_sdr...")
    rtl_dbfs, rtl_linear = measure_with_rtl_sdr(sample_rate)
    print(f"  Power (dBFS): {rtl_dbfs:.2f}")
    print(f"  Power (linear): {rtl_linear:.6f}")
    
    print("\nMeasuring with SoapySDR...")
    soap_dbfs, soap_linear = measure_with_soapysdr(sample_rate)
    print(f"  Power (dBFS): {soap_dbfs:.2f}")
    print(f"  Power (linear): {soap_linear:.6f}")
    
    diff = rtl_dbfs - soap_dbfs
    print(f"\nDifference (rtl_sdr - SoapySDR): {diff:.2f} dB")
    print(f"Ratio: rtl_sdr is {10**(diff/20):.3f}x the amplitude")
    
    time.sleep(2)
