#!/usr/bin/env python3
"""
Test: rtl_sdr gain parameter interpretation
Check if gain should be in dB or tenths-of-dB
"""

import subprocess
import numpy as np

def measure_with_rtl_sdr_gain(sample_rate=250000, gain_param=49.6):
    """Measure with rtl_sdr - test gain interpretation"""
    
    # Try both formats
    cmd_float = [
        'rtl_sdr',
        '-f', '144800000',
        '-s', str(sample_rate),
        '-g', str(gain_param),  # 49.6 dB
        '-n', str(int(sample_rate * 1)),
        '-'
    ]
    
    cmd_tenths = [
        'rtl_sdr',
        '-f', '144800000',
        '-s', str(sample_rate),
        '-g', str(int(gain_param * 10)),  # 496 (tenth-dB units)
        '-n', str(int(sample_rate * 1)),
        '-'
    ]
    
    results = []
    
    for label, cmd in [("49.6 dB", cmd_float), ("496 (10th-dB)", cmd_tenths)]:
        print(f"\nTesting: {label}")
        print(f"Command: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            chunk = process.stdout.read(sample_rate * 2)
            stderr = process.stderr.read()
            process.wait()
            
            if stderr:
                print(f"stderr: {stderr.decode()[:200]}")
            
            if chunk:
                uint8_data = np.frombuffer(chunk, dtype=np.uint8)
                float_data = (uint8_data.astype(np.float32) - 127.5) / 127.5
                iq_complex = float_data[0::2] + 1j * float_data[1::2]
                
                power = np.mean(np.abs(iq_complex)**2)
                power_dbfs = 10 * np.log10(power) if power > 0 else -200
                
                print(f"  Result: {power_dbfs:.2f} dBFS")
                results.append((label, power_dbfs))
            else:
                print(f"  ERROR: No data received")
        except Exception as e:
            print(f"  ERROR: {e}")
    
    if len(results) >= 2:
        diff = results[0][1] - results[1][1]
        print(f"\nDifference: {diff:.2f} dB")
        return results
    return []

print("="*70)
print("Testing rtl_sdr gain parameter format")
print("="*70)

results = measure_with_rtl_sdr_gain(250000)

print("\n" + "="*70)
print("ANALYSIS:")
print("="*70)
if results:
    for label, power in results:
        print(f"  {label:15s}: {power:.2f} dBFS")
