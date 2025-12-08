#!/usr/bin/env python3
"""
Measure noise floor WITHOUT csdr decimation
Direct from RTL-SDR → power measurement
"""

import sys
import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import time
import signal

def log(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()

def load_config(config_file):
    """Load configuration from .conf file"""
    config = {
        'device': 'rtlsdr',
        'frequency': 144.8,
        'sample_rate': 1024000,
        'agc': False,
        'gains': {},
        'settings': {}
    }
    
    try:
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                
                key, value = parts
                if '#' in value:
                    value = value.split('#')[0].strip()
                
                if key == 'FREQUENCY':
                    config['frequency'] = float(value)
                elif key == 'SAMPLE_RATE':
                    config['sample_rate'] = int(value)
                elif key == 'AGC':
                    config['agc'] = value.lower() in ('true', 'yes', '1', 'on')
                elif key == 'GAIN':
                    gain_parts = value.split(None, 1)
                    if len(gain_parts) == 2:
                        gain_name, gain_value = gain_parts
                        config['gains'][gain_name.upper()] = float(gain_value)
                elif key == 'SETTING':
                    setting_parts = value.split(None, 1)
                    if len(setting_parts) == 2:
                        setting_name, setting_value = setting_parts
                        if setting_value.lower() in ('true', 'false'):
                            config['settings'][setting_name] = setting_value.lower() == 'true'
                        else:
                            config['settings'][setting_name] = setting_value
        
        return config
    except Exception as e:
        log(f"Error loading config: {e}")
        return config

def setup_rtlsdr(sdr, config):
    """Configure RTL-SDR"""
    use_agc = config['agc']
    
    if use_agc:
        sdr.setGainMode(SOAPY_SDR_RX, 0, True)
        log("RTL-SDR AGC: enabled")
        return
    
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    log("RTL-SDR AGC: disabled (manual gain)")
    
    gains = config.get('gains', {})
    supported = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7,
                 16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8,
                 36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]
    requested = float(gains.get('TUNER', 40.0))
    requested = max(0.0, min(49.6, requested))
    gain = min(supported, key=lambda g: abs(g - requested))
    
    sdr.setGain(SOAPY_SDR_RX, 0, gain)
    log(f"RTL-SDR gain (TUNER): {gain} dB (requested {requested})")

def measure_direct():
    """Measure power directly from RTL-SDR without decimation"""
    
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'rtlsdr.conf'
    config = load_config(config_file)
    
    log("=" * 60)
    log("Direct RTL-SDR Noise Floor Measurement (NO DECIMATION)")
    log("=" * 60)
    log(f"Config: {config_file}")
    log(f"Frequency: {config['frequency']} MHz")
    log(f"Sample rate: {config['sample_rate']} Hz")
    log(f"Gain: {config['gains'].get('TUNER', 40.0)} dB")
    log("=" * 60)
    
    # Open RTL-SDR with device args (settings passed at initialization)
    device_args = {'driver': 'rtlsdr'}
    
    # Convert config settings to device args
    for setting_name, setting_value in config['settings'].items():
        if isinstance(setting_value, bool):
            device_args[setting_name] = '1' if setting_value else '0'
        else:
            device_args[setting_name] = str(setting_value)
    
    log(f"Opening device with args: {device_args}")
    sdr = SoapySDR.Device(device_args)
    
    # Configure device
    sdr.setSampleRate(SOAPY_SDR_RX, 0, config['sample_rate'])
    sdr.setFrequency(SOAPY_SDR_RX, 0, config['frequency'] * 1e6)
    setup_rtlsdr(sdr, config)
    
    log(f"Actual sample rate: {sdr.getSampleRate(SOAPY_SDR_RX, 0)} Hz")
    log(f"Actual frequency: {sdr.getFrequency(SOAPY_SDR_RX, 0)/1e6} MHz")
    log(f"Actual gain: {sdr.getGain(SOAPY_SDR_RX, 0)} dB")
    
    # Setup stream
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rx_stream)
    
    log("=" * 60)
    log("Measuring power every 100ms... Press Ctrl+C to stop")
    log("=" * 60)
    log(f"{'Time (s)':<12} {'Power (dBFS)':<15} {'Status'}")
    log("-" * 60)
    
    buff = np.zeros(4096, dtype=np.complex64)
    start_time = time.time()
    measurement_count = 0
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Samples per 100ms
    samples_per_100ms = int(config['sample_rate'] * 0.1)
    accumulated = np.array([], dtype=np.complex64)
    
    try:
        while running:
            sr = sdr.readStream(rx_stream, [buff], len(buff))
            if sr.ret > 0:
                accumulated = np.concatenate([accumulated, buff[:sr.ret]])
                
                # Process complete measurements
                while len(accumulated) >= samples_per_100ms:
                    samples = accumulated[:samples_per_100ms]
                    accumulated = accumulated[samples_per_100ms:]
                    
                    # Compute power in dBFS
                    power = np.mean(np.abs(samples)**2)
                    if power > 0:
                        power_dbfs = 10 * np.log10(power)
                    else:
                        power_dbfs = -100
                    
                    power_dbfs = max(-100, min(0, power_dbfs))
                    
                    elapsed = time.time() - start_time
                    measurement_count += 1
                    
                    status = "SIGNAL" if power_dbfs > -35 else "noise"
                    print(f"{elapsed:<12.1f} {power_dbfs:<15.1f} {status}")
                    sys.stdout.flush()
    
    except KeyboardInterrupt:
        pass
    finally:
        log("\nStopping...")
        sdr.deactivateStream(rx_stream)
        sdr.closeStream(rx_stream)
        
        elapsed = time.time() - start_time
        log(f"\nMeasurements: {measurement_count} in {elapsed:.1f}s")

if __name__ == '__main__':
    measure_direct()
