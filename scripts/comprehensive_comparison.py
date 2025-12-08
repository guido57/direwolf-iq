#!/usr/bin/env python3
"""
Comprehensive noise floor comparison: SoapySDR vs rtl_sdr
Tests multiple sample rates to understand degradation pattern
"""

import subprocess
import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import time
import sys

def measure_with_rtl_sdr(sample_rate=250000):
    """Measure with rtl_sdr - raw IQ format (tenths of dB gain)"""
    cmd = [
        'rtl_sdr',
        '-f', '144800000',
        '-s', str(sample_rate),
        '-g', str(int(49.6 * 10)),  # 496 tenths-of-dB
        '-n', str(int(sample_rate * 1.5)),
        '-'
    ]
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        
        powers = []
        bytes_total = 0
        
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            
            bytes_total += len(chunk)
            uint8_data = np.frombuffer(chunk, dtype=np.uint8)
            float_data = (uint8_data.astype(np.float32) - 127.5) / 127.5
            iq_complex = float_data[0::2] + 1j * float_data[1::2]
            
            power = np.mean(np.abs(iq_complex)**2)
            if power > 0:
                power_dbfs = 10 * np.log10(power)
                powers.append(power_dbfs)
        
        process.wait(timeout=5)
        
        if powers:
            return np.mean(powers), len(powers)
        return None, 0
    except Exception as e:
        print(f"  rtl_sdr error: {e}", file=sys.stderr)
        return None, 0

def measure_with_soapysdr(sample_rate=250000):
    """Measure with SoapySDR - CF32 format"""
    try:
        sdr = SoapySDR.Device({'driver': 'rtlsdr'})
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
        sdr.setGainMode(SOAPY_SDR_RX, 0, False)
        sdr.setGain(SOAPY_SDR_RX, 0, 49.6)
        
        rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rx_stream)
        
        buff = np.zeros(4096, dtype=np.complex64)
        for _ in range(10):
            sdr.readStream(rx_stream, [buff], len(buff))
        
        time.sleep(0.2)
        
        powers = []
        for _ in range(20):
            sr = sdr.readStream(rx_stream, [buff], len(buff))
            if sr.ret > 0:
                samples = buff[:sr.ret]
                power = np.mean(np.abs(samples)**2)
                if power > 0:
                    power_dbfs = 10 * np.log10(power)
                    powers.append(power_dbfs)
            time.sleep(0.05)
        
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        del sdr
        
        if powers:
            return np.mean(powers), len(powers)
        return None, 0
    except Exception as e:
        print(f"  SoapySDR error: {e}", file=sys.stderr)
        return None, 0

print("="*80)
print("COMPREHENSIVE NOISE FLOOR COMPARISON: SoapySDR vs rtl_sdr")
print("="*80)
print("\nDevice: Raspberry Pi Zero 2 W + RTL2832U (R820T)")
print("Frequency: 144.8 MHz")
print("Gain: 49.6 dB")
print("="*80)

results = {}

for sample_rate in [250000, 1024000, 2048000]:
    print(f"\n{'='*80}")
    print(f"Sample Rate: {sample_rate:,} Hz ({sample_rate/1000:.0f} kHz)")
    print(f"{'='*80}")
    
    print("\nMeasuring with SoapySDR...")
    soap_power, soap_count = measure_with_soapysdr(sample_rate)
    if soap_power:
        print(f"  Result: {soap_power:.2f} dBFS ({soap_count} samples)")
    else:
        print(f"  FAILED")
    
    time.sleep(2)
    
    print("\nMeasuring with rtl_sdr...")
    rtl_power, rtl_count = measure_with_rtl_sdr(sample_rate)
    if rtl_power:
        print(f"  Result: {rtl_power:.2f} dBFS ({rtl_count} samples)")
    else:
        print(f"  FAILED")
    
    if soap_power and rtl_power:
        diff = rtl_power - soap_power
        results[sample_rate] = {
            'soapysdr': soap_power,
            'rtl_sdr': rtl_power,
            'difference': diff,
        }
        print(f"\n  Difference (rtl_sdr - SoapySDR): {diff:+.2f} dB")

print(f"\n\n{'='*80}")
print("SUMMARY TABLE")
print(f"{'='*80}")
print(f"{'Sample Rate':<15} {'SoapySDR':<15} {'rtl_sdr':<15} {'Difference':<15}")
print(f"{'-'*60}")

for rate in sorted(results.keys()):
    r = results[rate]
    print(f"{rate:>10,} Hz  {r['soapysdr']:>10.2f} dBFS  {r['rtl_sdr']:>10.2f} dBFS  {r['difference']:>+10.2f} dB")

# Calculate degradation vs sample rate for each method
print(f"\n\n{'='*80}")
print("SAMPLE RATE DEGRADATION")
print(f"{'='*80}")

if 250000 in results:
    base_soap = results[250000]['soapysdr']
    base_rtl = results[250000]['rtl_sdr']
    
    print(f"\nDegradation from 250 kHz baseline:")
    print(f"{'Rate':<15} {'SoapySDR':<20} {'rtl_sdr':<20}")
    print(f"{'-'*55}")
    
    for rate in sorted(results.keys()):
        r = results[rate]
        soap_deg = r['soapysdr'] - base_soap
        rtl_deg = r['rtl_sdr'] - base_rtl
        print(f"{rate:>10,} Hz  {soap_deg:>+10.2f} dB         {rtl_deg:>+10.2f} dB")
