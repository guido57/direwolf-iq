#!/usr/bin/env python3
"""
Measure noise floor using rtl_fm directly (bypasses SoapySDR)
Compares rtl_fm performance on Ubuntu vs Raspberry Pi
"""

import subprocess
import numpy as np
import struct
import sys
import platform
import time
import signal

def measure_noise_floor_rtl_fm(sample_rate=250000, frequency=144.8, gain=49.6, duration=2):
    """Measure noise floor using rtl_sdr (raw IQ capture)"""
    
    print("="*70)
    print("RTL-SDR Noise Floor via rtl_sdr (Direct librtlsdr)")
    print("="*70)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    
    print(f"\nTest parameters:")
    print(f"  Frequency: {frequency} MHz")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Gain: {gain} dB")
    print(f"  Duration: {duration} seconds")
    
    # rtl_sdr command to stream raw IQ samples to stdout
    # -f: frequency in Hz
    # -s: sample rate
    # -g: gain in dB
    # -: output to stdout
    num_samples = int(sample_rate * duration)
    
    cmd = [
        'rtl_sdr',
        '-f', f'{int(frequency * 1e6)}',
        '-s', str(sample_rate),
        '-g', str(int(gain * 10)),  # rtl_sdr expects tenths of dB!
        '-n', str(num_samples),
        '-'
    ]
    
    print(f"\nRunning: {' '.join(cmd)}")
    
    try:
        # Start rtl_sdr process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        
        print("Measuring noise floor...")
        powers = []
        bytes_read = 0
        
        # Read raw IQ data from rtl_sdr (uint8 format)
        while True:
            try:
                # Read 4KB chunks of uint8 IQ data
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                
                bytes_read += len(chunk)
                
                # rtl_sdr outputs uint8 (0-255) where 127.5 is center
                # Each I and Q sample is one uint8, so pairs of bytes
                uint8_data = np.frombuffer(chunk, dtype=np.uint8)
                
                # Convert uint8 to float (-1 to +1 range)
                float_data = (uint8_data.astype(np.float32) - 127.5) / 127.5
                
                # Convert to complex IQ
                iq_complex = float_data[0::2] + 1j * float_data[1::2]
                
                # Compute power in dBFS
                power = np.mean(np.abs(iq_complex)**2)
                if power > 0:
                    power_dbfs = 10 * np.log10(power)
                    powers.append(power_dbfs)
                
            except Exception as e:
                print(f"  Error reading data: {e}")
                break
        
        # Wait for process to finish
        process.wait(timeout=5)
        
        # Statistics
        if powers:
            avg_power = np.mean(powers)
            std_power = np.std(powers)
            min_power = np.min(powers)
            max_power = np.max(powers)
            
            print("\n" + "="*70)
            print("RESULTS:")
            print("="*70)
            print(f"Samples collected: {len(powers)}")
            print(f"Bytes read: {bytes_read} ({bytes_read/1024:.1f} KB)")
            print(f"Average noise floor: {avg_power:.2f} dBFS")
            print(f"Std deviation:       {std_power:.2f} dB")
            print(f"Min:                 {min_power:.2f} dBFS")
            print(f"Max:                 {max_power:.2f} dBFS")
            print("="*70)
            
            return avg_power
        else:
            print("ERROR: No data collected")
            return None
            
    except FileNotFoundError:
        print("ERROR: rtl_sdr not found. Install with: sudo apt install rtl-sdr")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    try:
        # Test at multiple sample rates
        for rate in [250000, 1024000]:
            print("\n\n")
            measure_noise_floor_rtl_fm(sample_rate=rate, duration=1.5)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nAborted by user")
