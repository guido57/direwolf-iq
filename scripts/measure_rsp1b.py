#!/usr/bin/env python3
"""
Noise floor comparison: RSP1B on Ubuntu vs Raspberry Pi
Tests multiple sample rates to characterize platform differences
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import numpy as np
import time
import sys
import platform

def measure_noise_floor_rsp1b(sample_rates=[250000, 1024000, 2048000]):
    """Measure noise floor with RSP1B at multiple sample rates"""
    
    print("="*80)
    print("RSP1B NOISE FLOOR MEASUREMENT")
    print("="*80)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")
    
    try:
        # Open RSP1B device - auto-detect serial
        print("\nOpening RSP1B...")
        # First try to find any SDRplay device
        devices = SoapySDR.Device.enumerate({'driver': 'sdrplay'})
        if not devices:
            raise RuntimeError("No SDRplay devices found!")
        
        print(f"Found SDRplay device: {devices[0]}")
        sdr = SoapySDR.Device(devices[0])
        
        print(f"Device: {sdr.getDriverKey()}")
        print(f"Hardware: {sdr.getHardwareKey()}")
        
        results = {}
        
        for sample_rate in sample_rates:
            print(f"\n{'='*80}")
            print(f"Sample Rate: {sample_rate:,} Hz ({sample_rate/1000:.0f} kHz)")
            print(f"{'='*80}")
            
            try:
                # Configure device
                sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
                sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
                
                # Set gain to auto initially, then check actual value
                sdr.setGainMode(SOAPY_SDR_RX, 0, True)  # Auto gain
                
                # Get actual settings
                actual_rate = sdr.getSampleRate(SOAPY_SDR_RX, 0)
                actual_freq = sdr.getFrequency(SOAPY_SDR_RX, 0)
                actual_gain = sdr.getGain(SOAPY_SDR_RX, 0)
                
                print(f"\nDevice settings:")
                print(f"  Sample rate: {actual_rate:,.0f} Hz")
                print(f"  Frequency: {actual_freq/1e6:.1f} MHz")
                print(f"  Gain (Auto): {actual_gain:.1f} dB")
                
                # Setup stream
                rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
                sdr.activateStream(rx_stream)
                
                # Warmup
                buff = np.zeros(4096, dtype=np.complex64)
                for _ in range(10):
                    sdr.readStream(rx_stream, [buff], len(buff))
                
                time.sleep(0.5)
                
                # Measure noise floor
                print(f"\nMeasuring noise floor (20 samples)...")
                powers = []
                
                for i in range(20):
                    sr = sdr.readStream(rx_stream, [buff], len(buff))
                    if sr.ret > 0:
                        samples = buff[:sr.ret]
                        power = np.mean(np.abs(samples)**2)
                        if power > 0:
                            power_dbfs = 10 * np.log10(power)
                            powers.append(power_dbfs)
                    time.sleep(0.05)
                
                # Statistics
                if powers:
                    avg_power = np.mean(powers)
                    std_power = np.std(powers)
                    min_power = np.min(powers)
                    max_power = np.max(powers)
                    
                    print(f"\n{'RESULTS':^80}")
                    print(f"{'-'*80}")
                    print(f"Average noise floor: {avg_power:.2f} dBFS")
                    print(f"Std deviation:       {std_power:.2f} dB")
                    print(f"Min:                 {min_power:.2f} dBFS")
                    print(f"Max:                 {max_power:.2f} dBFS")
                    
                    results[sample_rate] = {
                        'avg': avg_power,
                        'std': std_power,
                        'min': min_power,
                        'max': max_power,
                        'gain': actual_gain,
                    }
                else:
                    print("ERROR: No data collected")
                
                # Cleanup
                sdr.deactivateStream(rx_stream)
                sdr.closeStream(rx_stream)
                
                time.sleep(1)
                
            except Exception as e:
                print(f"ERROR: {e}")
                import traceback
                traceback.print_exc()
        
        del sdr
        
        # Summary
        if results:
            print(f"\n\n{'='*80}")
            print("SUMMARY TABLE")
            print(f"{'='*80}")
            print(f"{'Sample Rate':<15} {'Noise Floor':<15} {'Std Dev':<15} {'Gain':<10}")
            print(f"{'-'*55}")
            
            for rate in sorted(results.keys()):
                r = results[rate]
                print(f"{rate:>10,} Hz  {r['avg']:>10.2f} dBFS  {r['std']:>10.2f} dB  {r['gain']:>6.1f} dB")
            
            # Calculate degradation
            if 250000 in results:
                base = results[250000]['avg']
                print(f"\n{'='*80}")
                print("SAMPLE RATE DEGRADATION")
                print(f"{'='*80}")
                print(f"{'Rate':<15} {'Degradation':<15}")
                print(f"{'-'*30}")
                
                for rate in sorted(results.keys()):
                    deg = results[rate]['avg'] - base
                    print(f"{rate:>10,} Hz  {deg:>+10.2f} dB")
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    success = measure_noise_floor_rsp1b([250000, 1024000, 2048000])
    sys.exit(0 if success else 1)
