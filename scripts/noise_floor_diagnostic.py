#!/usr/bin/env python3
"""
Noise floor diagnostic for SDRs (RTL-SDR, SDRplay, etc.)
Measures dBFS noise floor using SoapySDR with identical settings.
Select device via --device rtlsdr|sdrplay and optional device-specific gains.
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX
import numpy as np
import time
import sys
import platform
import argparse

def measure_noise_floor(args):
    """Measure noise floor with selected device and settings"""
    
    print("[diag] Entering measure_noise_floor()")
    print("="*70)
    print("SDR Noise Floor Diagnostic")
    print("="*70)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")
    
    # Parameters from CLI
    FREQUENCY = args.freq * 1e6
    SAMPLE_RATE = int(args.rate)
    DEVICE = args.device
    # Generic gain (RTL-SDR tuner dB or SDRplay IFGR)
    GAIN = float(args.gain)
    RFGR = int(args.rfgr) if args.rfgr is not None else None
    
    print(f"\nTest parameters:")
    print(f"  Frequency: {FREQUENCY/1e6} MHz")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    print(f"  Gain: {GAIN} dB")
    
    # Open device
    print(f"\nOpening SDR: {DEVICE}...")
    sdr = SoapySDR.Device({'driver': DEVICE})
    
    # Configure
    sdr.setSampleRate(SOAPY_SDR_RX, 0, SAMPLE_RATE)
    sdr.setFrequency(SOAPY_SDR_RX, 0, FREQUENCY)
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    # Device-specific gain handling
    if DEVICE == 'rtlsdr':
        sdr.setGain(SOAPY_SDR_RX, 0, GAIN)
        try:
            sdr.writeSetting('digital_agc', 'false')
            sdr.writeSetting('offset_tune', 'false')
        except Exception:
            pass
    elif DEVICE == 'sdrplay':
        # SDRplay uses IFGR/RFGR; set if provided
        try:
            sdr.setGain(SOAPY_SDR_RX, 0, 'IFGR', int(GAIN))
        except Exception:
            # Fallback to generic gain setter
            sdr.setGain(SOAPY_SDR_RX, 0, GAIN)
        if RFGR is not None:
            try:
                sdr.setGain(SOAPY_SDR_RX, 0, 'RFGR', RFGR)
            except Exception:
                pass
    
    # Harden device settings (explicitly disable optional DSP that can vary)
    try:
        sdr.writeSetting('biastee', 'false')
    except Exception:
        pass

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
    
    # Setup stream with explicit buffer sizing to reduce overflows
    print("\nStarting stream...")
    # Use string format 'CF32' per SoapySDR Python API; kwargs values as strings
    # Smaller buffers + more ring buffers tend to behave better on some hosts
    stream_args = {'bufflen': '16384', 'buffers': '16', 'asyncBuffs': '4'}
    try:
        rx_stream = sdr.setupStream(SOAPY_SDR_RX, 'CF32', [0], stream_args)
    except TypeError:
        # Fallback without kwargs
        rx_stream = sdr.setupStream(SOAPY_SDR_RX, 'CF32', [0])
    sdr.activateStream(rx_stream)
    
    # Warmup
    buff = np.zeros(2048, dtype=np.complex64)
    timeout_us = 1000000  # 1000 ms timeout: long enough, reduces stalls
    warm_ok = 0
    for _ in range(10):
        sr = sdr.readStream(rx_stream, [buff], len(buff), timeoutUs=timeout_us)
        if sr.ret > 0:
            warm_ok += 1
        elif sr.ret == 0:
            # timeout, continue trying
            continue
        else:
            print(f"  Warmup read error: {sr.ret}")
    
    time.sleep(0.5)
    
    # Take measurements
    print("\nMeasuring noise floor (20 samples)...")
    powers = []
    
    for i in range(20):
        # Try a few times per sample to ride out transient overflows
        attempt = 0
        got_data = False
        while attempt < 3 and not got_data:
            sr = sdr.readStream(rx_stream, [buff], len(buff), timeoutUs=timeout_us)
            if sr.ret > 0:
                samples = buff[:sr.ret]
                power_rms = np.mean(np.abs(samples)**2)
                if power_rms > 0:
                    power_dbfs = 10 * np.log10(power_rms)
                    powers.append(power_dbfs)
                    if i % 5 == 0 and attempt == 0:
                        print(f"  Sample {i+1:2d}: {power_dbfs:.2f} dBFS")
                got_data = True
            elif sr.ret == 0:
                # timeout, retry
                attempt += 1
                continue
            else:
                # overflow or other error; retry a couple times before logging
                attempt += 1
                if attempt >= 3:
                    print(f"  Read error: {sr.ret}")
        if not got_data:
            powers.append(np.nan)
        time.sleep(0.05)
    
    # Statistics
    # Filter out NaNs from timeouts
    valid = [p for p in powers if not np.isnan(p)]
    if valid:
        avg_power = np.mean(valid)
        std_power = np.std(valid)
        min_power = np.min(valid)
        max_power = np.max(valid)
    else:
        avg_power = float('nan')
        std_power = float('nan')
        min_power = float('nan')
        max_power = float('nan')
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(f"Average noise floor: {avg_power:.2f} dBFS")
    print(f"Std deviation:       {std_power:.2f} dB")
    print(f"Min:                 {min_power:.2f} dBFS")
    print(f"Max:                 {max_power:.2f} dBFS")
    print("="*70)
    
    # Cleanup
    try:
        sdr.deactivateStream(rx_stream)
    except Exception:
        pass
    try:
        sdr.closeStream(rx_stream)
    except Exception:
        pass
    
    return avg_power

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SDR Noise Floor Diagnostic')
    parser.add_argument('--device', choices=['rtlsdr', 'sdrplay'], default='rtlsdr', help='SDR driver')
    parser.add_argument('--freq', type=float, default=144.8, help='Frequency in MHz')
    parser.add_argument('--rate', type=int, default=250000, help='Sample rate in Hz')
    parser.add_argument('--gain', type=float, default=49.6, help='Gain: RTL tuner dB or SDRplay IFGR')
    parser.add_argument('--rfgr', type=int, help='SDRplay RF Gain Reduction (0-3)')
    args = parser.parse_args()

    try:
        try:
            SoapySDR.setLogLevel(SoapySDR.SOAPY_SDR_WARNING)
        except Exception:
            pass
        print("[diag] Starting noise floor diagnostic script")
        measure_noise_floor(args)
    except KeyboardInterrupt:
        print("\nAborted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
