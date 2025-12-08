#!/usr/bin/env python3
"""
Comprehensive RTL-SDR comparison test
Measures noise floor with identical settings
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import time
import sys
import platform

def measure_noise_floor():
    """Measure noise floor with fixed settings"""
    
    print("="*70)
    print("RTL-SDR Noise Floor Diagnostic")
    print("="*70)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")
    
    # Fixed test parameters
    FREQUENCY = 144.8e6
    SAMPLE_RATE = 250000
    GAIN = 49.6
    
    print(f"\nTest parameters:")
    print(f"  Frequency: {FREQUENCY/1e6} MHz")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    print(f"  Gain: {GAIN} dB")
    
    # Open device
    print("\nOpening RTL-SDR...")
    sdr = SoapySDR.Device({'driver': 'rtlsdr'})
    
    # Configure
    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMPLE_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQUENCY)
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    sdr.setGain(SOAPY_SDR_RX, 0, GAIN)
    
    # Read back actual settings
    actual_rate = sdr.getSampleRate(SOAPY_SDR_RX, 0)
    actual_freq = sdr.getFrequency(SOAPY_SDR_RX, 0)
    actual_gain = sdr.getGain(SOAPY_SDR_RX, 0)
    actual_bw = sdr.getBandwidth(SOAPY_SDR_RX, 0)
    
    print(f"\nActual device settings:")
    print(f"  Sample rate: {actual_rate} Hz")
    print(f"  Frequency: {actual_freq/1e6} MHz")
    print(f"  Gain: {actual_gain} dB")
    print(f"  Bandwidth: {actual_bw/1e3} kHz")
    
    # Check all settings
    try:
        print(f"\nRTL-SDR settings:")
        for key in ['offset_tune', 'digital_agc', 'biastee']:
            try:
                val = sdr.readSetting(key)
                print(f"  {key}: {val}")
            except:
                pass
    except:
        pass
    
    # Setup stream
    print("\nStarting stream...")
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
    
    # Warmup
    buff = np.zeros(4096, dtype=np.complex64)
    for _ in range(10):
        sdr.readStream(rx_stream, [buff], len(buff))
    
    time.sleep(0.5)
    
    # Take measurements
    print("\nMeasuring noise floor (20 samples)...")
    powers = []
    
    for i in range(20):
        sr = sdr.readStream(rx_stream, [buff], len(buff))
        if sr.ret > 0:
            samples = buff[:sr.ret]
            
            # Multiple power calculation methods
            power_rms = np.mean(np.abs(samples)**2)
            power_peak = np.max(np.abs(samples)**2)
            
            if power_rms > 0:
                power_dbfs = 10 * np.log10(power_rms)
                powers.append(power_dbfs)
                
                if i % 5 == 0:
                    print(f"  Sample {i+1:2d}: {power_dbfs:.2f} dBFS")
        
        time.sleep(0.05)
    
    # Statistics
    avg_power = np.mean(powers)
    std_power = np.std(powers)
    min_power = np.min(powers)
    max_power = np.max(powers)
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(f"Average noise floor: {avg_power:.2f} dBFS")
    print(f"Std deviation:       {std_power:.2f} dB")
    print(f"Min:                 {min_power:.2f} dBFS")
    print(f"Max:                 {max_power:.2f} dBFS")
    print("="*70)
    
    # Cleanup
    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    
    return avg_power

if __name__ == '__main__':
    try:
        measure_noise_floor()
    except KeyboardInterrupt:
        print("\nAborted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
