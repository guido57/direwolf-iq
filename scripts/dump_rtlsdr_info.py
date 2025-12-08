#!/usr/bin/env python3
"""
Dump all RTL-SDR settings and capabilities via SoapySDR
"""

import SoapySDR
from SoapySDR import SOAPY_SDR_RX

def dump_rtlsdr_info():
    print("=" * 70)
    print("RTL-SDR Device Information via SoapySDR")
    print("=" * 70)
    
    try:
        sdr = SoapySDR.Device({'driver': 'rtlsdr'})
    except Exception as e:
        print(f"ERROR: Could not open RTL-SDR: {e}")
        return
    
    print("\n### Hardware Info ###")
    print(f"Hardware Key: {sdr.getHardwareKey()}")
    try:
        print(f"Hardware Info: {sdr.getHardwareInfo()}")
    except:
        print("Hardware Info: Not available")
    
    print("\n### Frequency Range ###")
    freq_ranges = sdr.getFrequencyRange(SOAPY_SDR_RX, 0)
    for fr in freq_ranges:
        print(f"  {fr.minimum()/1e6:.3f} - {fr.maximum()/1e6:.3f} MHz")
    
    print("\n### Sample Rate Range ###")
    rate_ranges = sdr.getSampleRateRange(SOAPY_SDR_RX, 0)
    for rr in rate_ranges:
        print(f"  {rr.minimum()/1e6:.3f} - {rr.maximum()/1e6:.3f} MSps")
    
    print("\n### Gain Range ###")
    gain_range = sdr.getGainRange(SOAPY_SDR_RX, 0)
    print(f"  Overall: {gain_range.minimum()} - {gain_range.maximum()} dB")
    
    gain_names = sdr.listGains(SOAPY_SDR_RX, 0)
    print(f"  Gain elements: {gain_names}")
    for name in gain_names:
        gr = sdr.getGainRange(SOAPY_SDR_RX, 0, name)
        print(f"    {name}: {gr.minimum()} - {gr.maximum()} dB")
    
    print("\n### Bandwidth Range ###")
    bw_ranges = sdr.getBandwidthRange(SOAPY_SDR_RX, 0)
    for bw in bw_ranges:
        print(f"  {bw.minimum()/1e6:.3f} - {bw.maximum()/1e6:.3f} MHz")
    
    print("\n### Antennas ###")
    antennas = sdr.listAntennas(SOAPY_SDR_RX, 0)
    print(f"  Available: {antennas}")
    print(f"  Current: {sdr.getAntenna(SOAPY_SDR_RX, 0)}")
    
    print("\n### AGC Support ###")
    print(f"  Has AGC Mode: {sdr.hasGainMode(SOAPY_SDR_RX, 0)}")
    if sdr.hasGainMode(SOAPY_SDR_RX, 0):
        print(f"  AGC Enabled: {sdr.getGainMode(SOAPY_SDR_RX, 0)}")
    
    print("\n### Settings ###")
    settings = sdr.getSettingInfo()
    for setting in settings:
        print(f"  {setting.key}:")
        print(f"    Type: {setting.type}")
        print(f"    Description: {setting.description}")
        if setting.options:
            print(f"    Options: {setting.options}")
        try:
            value = sdr.readSetting(setting.key)
            print(f"    Current: {value}")
        except:
            print(f"    Current: (cannot read)")
    
    print("\n### Stream Formats ###")
    formats = sdr.getStreamFormats(SOAPY_SDR_RX, 0)
    print(f"  Supported: {formats}")
    
    print("\n### Current Configuration ###")
    try:
        sdr.setFrequency(SOAPY_SDR_RX, 0, 144.8e6)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, 250000)
        print(f"  Frequency: {sdr.getFrequency(SOAPY_SDR_RX, 0)/1e6:.6f} MHz")
        print(f"  Sample Rate: {sdr.getSampleRate(SOAPY_SDR_RX, 0)} Hz")
        print(f"  Bandwidth: {sdr.getBandwidth(SOAPY_SDR_RX, 0)/1e6:.3f} MHz")
    except Exception as e:
        print(f"  Error reading config: {e}")
    
    print("\n### Frontend Corrections ###")
    try:
        print(f"  DC Offset Mode: {sdr.hasDCOffsetMode(SOAPY_SDR_RX, 0)}")
        if sdr.hasDCOffsetMode(SOAPY_SDR_RX, 0):
            print(f"    Enabled: {sdr.getDCOffsetMode(SOAPY_SDR_RX, 0)}")
    except:
        pass
    
    try:
        print(f"  Frequency Correction: {sdr.hasFrequencyCorrection(SOAPY_SDR_RX, 0)}")
        if sdr.hasFrequencyCorrection(SOAPY_SDR_RX, 0):
            print(f"    PPM: {sdr.getFrequencyCorrection(SOAPY_SDR_RX, 0)}")
    except:
        pass
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    dump_rtlsdr_info()
