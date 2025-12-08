#!/usr/bin/env python3
"""
Quick test: Does rtl_sdr gain work in dB or tenths-of-dB?
"""
import subprocess
import numpy as np
import sys

def quick_measure(gain_param, label):
    """Quick 250ms measurement"""
    cmd = ['rtl_sdr', '-f', '144800000', '-s', '250000', '-g', str(gain_param), '-n', '62500', '-']
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        chunk = process.stdout.read(250000)  # 250KB max
        process.terminate()
        process.wait(timeout=2)
        
        if chunk and len(chunk) > 100:
            uint8_data = np.frombuffer(chunk, dtype=np.uint8)
            float_data = (uint8_data.astype(np.float32) - 127.5) / 127.5
            iq_complex = float_data[0::2] + 1j * float_data[1::2]
            power = np.mean(np.abs(iq_complex)**2)
            power_dbfs = 10 * np.log10(power) if power > 0 else -200
            return power_dbfs
    except:
        pass
    return None

print("Quick gain test (250 kHz, 250ms capture):")
print()

result_49 = quick_measure(49.6, "49.6 dB")
result_496 = quick_measure(496, "496 (10th-dB?)")

if result_49 is not None:
    print(f"  -g 49.6:  {result_49:.1f} dBFS")
if result_496 is not None:
    print(f"  -g 496:   {result_496:.1f} dBFS")

if result_49 is not None and result_496 is not None:
    diff = result_49 - result_496
    print(f"\nDifference: {diff:.1f} dB ({result_49} vs {result_496})")
    if abs(diff) > 15:
        print("→ Gain likely uses TENTHS of dB (496 = 49.6 dB)")
    elif abs(diff) < 5:
        print("→ Both formats work similarly")
    else:
        print("→ Unclear - may use different scales")
