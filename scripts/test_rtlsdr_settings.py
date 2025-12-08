#!/usr/bin/env python3
"""
Test if bias-tee or other hidden settings are causing the noise floor difference
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX
import sys

def test_settings():
    print("Testing RTL-SDR settings that might affect noise floor...")
    print("=" * 70)
    
    sdr = SoapySDR.Device({'driver': 'rtlsdr'})
    
    # Configure basic settings
    sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
    sdr.setSampleRate(SOAPY_SDR_RX, 0, 250000)
    sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    sdr.setGain(SOAPY_SDR_RX, 0, 49.6)
    
    print("\n### Testing Bias-Tee ###")
    try:
        current = sdr.readSetting('biastee')
        print(f"  Current: {current}")
        
        # Try disabling
        sdr.writeSetting('biastee', 'false')
        print(f"  Set to: false")
        print(f"  Verify: {sdr.readSetting('biastee')}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### Testing Direct Sampling ###")
    try:
        current = sdr.readSetting('direct_samp')
        print(f"  Current: {current}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### Testing Offset Tuning ###")
    try:
        current = sdr.readSetting('offset_tune')
        print(f"  INITIAL DEFAULT: {current}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### Testing Digital AGC ###")
    try:
        current = sdr.readSetting('digital_agc')
        print(f"  Current: {current}")
        
        # Ensure it's disabled
        sdr.writeSetting('digital_agc', 'false')
        print(f"  Set to false: {sdr.readSetting('digital_agc')}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### Testing RF AGC ###")
    try:
        # This is different from gain mode
        settings = sdr.getSettingInfo()
        for s in settings:
            if 'agc' in s.key.lower():
                try:
                    val = sdr.readSetting(s.key)
                    print(f"  {s.key}: {val}")
                except:
                    pass
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### Testing Tuner Bandwidth ###")
    try:
        current_bw = sdr.getBandwidth(SOAPY_SDR_RX, 0)
        print(f"  Current bandwidth: {current_bw/1e6:.3f} MHz")
        
        # Try setting to 0 (automatic)
        sdr.setBandwidth(SOAPY_SDR_RX, 0, 0)
        print(f"  Set to 0 (auto): {sdr.getBandwidth(SOAPY_SDR_RX, 0)/1e6:.3f} MHz")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n### All Available Settings ###")
    settings = sdr.getSettingInfo()
    for setting in settings:
        try:
            value = sdr.readSetting(setting.key)
            print(f"  {setting.key} = {value}")
            if setting.description:
                print(f"    ({setting.description})")
        except:
            print(f"  {setting.key} = (cannot read)")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    test_settings()
