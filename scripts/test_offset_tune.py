#!/usr/bin/env python3
"""
Test offset_tune effect on noise floor
Compare offset_tune=0 vs offset_tune=1
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import time

def test_noise_floor(offset_tune_value):
    """Test noise floor with specific offset_tune setting"""
    print(f"\n{'='*60}")
    print(f"Testing with offset_tune={offset_tune_value}")
    print('='*60)
    
    sdr = SoapySDR.Device({'driver': 'rtlsdr', 'offset_tune': str(offset_tune_value)})
    sdr.setSampleRate(SOAPY_SDR_RX, 0, 250000)
    sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    sdr.setGain(SOAPY_SDR_RX, 0, 49.6)
    
    print(f"offset_tune readSetting: {sdr.readSetting('offset_tune')}")
    print(f"Frequency: {sdr.getFrequency(SOAPY_SDR_RX, 0)/1e6} MHz")
    print(f"Gain: {sdr.getGain(SOAPY_SDR_RX, 0)} dB")
    
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
    
    buff = np.zeros(25000, dtype=np.complex64)
    time.sleep(1.0)  # Let it stabilize
    
    # Take 10 measurements
    powers = []
    for i in range(10):
        sr = sdr.readStream(rx_stream, [buff], len(buff))
        if sr.ret > 0:
            samples = buff[:sr.ret]
            power = np.mean(np.abs(samples)**2)
            power_dbfs = 10 * np.log10(power) if power > 0 else -100
            powers.append(power_dbfs)
            print(f"  Measurement {i+1}: {power_dbfs:.1f} dBFS")
        time.sleep(0.1)
    
    avg_power = np.mean(powers)
    print(f"\nAverage noise floor: {avg_power:.1f} dBFS")
    
    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    
    return avg_power

if __name__ == '__main__':
    print("RTL-SDR Offset Tune Comparison Test")
    
    # Test with offset_tune disabled
    noise_off = test_noise_floor(0)
    
    time.sleep(2)
    
    # Test with offset_tune enabled
    noise_on = test_noise_floor(1)
    
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    print(f"Noise floor with offset_tune=0: {noise_off:.1f} dBFS")
    print(f"Noise floor with offset_tune=1: {noise_on:.1f} dBFS")
    print(f"Difference: {noise_on - noise_off:.1f} dB")
    print("="*60)
