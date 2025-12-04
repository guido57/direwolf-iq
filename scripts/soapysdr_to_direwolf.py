#!/usr/bin/env python3
"""
Stream IQ samples from any SoapySDR-supported device to direwolf via stdout.
Supports: SDRplay RSP1/RSP2, RTL-SDR, Airspy, HackRF, and other SoapySDR devices.

Requires: python3-soapysdr
Install: sudo apt install python3-soapysdr

Usage: 
  python3 soapysdr_to_direwolf.py [options]
  python3 soapysdr_to_direwolf.py --config soapysdr.conf
  python3 soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --gain 40

Options:
  --config FILE      Configuration file (default: soapysdr.conf)
  --device TYPE      Device type (sdrplay, rtlsdr, airspy, hackrf, auto)
  --freq MHz         Frequency in MHz (default: 144.8)
  --gain VALUE       Gain in dB (device-specific, see config file)
  --agc              Enable automatic gain control
  --list-devices     List all available SoapySDR devices and exit

Device-specific gain settings (when not using config file):
  SDRplay:  --ifgr 23 --rfgr 0
  RTL-SDR:  --gain 40.0
  Airspy:   --lna 10 --mixer 10 --vga 10
  HackRF:   --lna 16 --vga 20
"""

import sys
import argparse
import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

def log(msg):
    """Print to stderr so it doesn't interfere with IQ data on stdout"""
    print(msg, file=sys.stderr)

def list_devices():
    """List all available SoapySDR devices"""
    log("Available SoapySDR devices:")
    log("-" * 60)
    results = SoapySDR.Device.enumerate()
    if not results:
        log("No devices found!")
        return
    
    for i, result in enumerate(results):
        log(f"\nDevice #{i}:")
        for key, value in result.items():
            log(f"  {key}: {value}")
    log("-" * 60)

def detect_device():
    """Auto-detect first available device"""
    results = SoapySDR.Device.enumerate()
    if not results:
        log("ERROR: No SoapySDR devices found!")
        sys.exit(1)
    
    device_info = results[0]
    # Convert SoapySDR kwargs object to dict
    device_dict = dict(device_info)
    driver = device_dict.get('driver', 'unknown')
    log(f"Auto-detected device: {driver}")
    
    # Log device details
    for key, value in device_dict.items():
        if key != 'driver':
            log(f"  {key}: {value}")
    
    return driver, device_dict

def load_config(config_file):
    """Load configuration from .conf file (direwolf-style format)"""
    try:
        config = {
            'device': None,
            'frequency': 144.8,
            'sample_rate': 192000,
            'agc': False,
            'antenna': None,
            'gains': {},
            'settings': {}
        }
        
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY VALUE format
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                
                key, value = parts[0].upper(), parts[1]
                
                # Strip inline comments from value
                if '#' in value:
                    value = value.split('#')[0].strip()
                else:
                    value = value.strip()
                
                if key == 'DEVICE':
                    # Parse device string (e.g., "driver=sdrplay" or "driver=sdrplay serial=123")
                    device_dict = {}
                    for item in value.split():
                        if '=' in item:
                            k, v = item.split('=', 1)
                            device_dict[k] = v
                    config['device'] = device_dict if device_dict else value
                elif key == 'FREQUENCY':
                    config['frequency'] = float(value)
                elif key == 'SAMPLE_RATE':
                    config['sample_rate'] = int(value)
                elif key == 'AGC':
                    config['agc'] = value.lower() in ('true', 'yes', '1', 'on')
                elif key == 'ANTENNA':
                    config['antenna'] = value.strip('"')
                elif key == 'GAIN':
                    # GAIN NAME VALUE format
                    gain_parts = value.split(None, 1)
                    if len(gain_parts) == 2:
                        gain_name, gain_value = gain_parts
                        try:
                            config['gains'][gain_name.upper()] = float(gain_value)
                        except ValueError:
                            config['gains'][gain_name.upper()] = int(gain_value)
                elif key == 'SETTING':
                    # SETTING NAME VALUE format
                    setting_parts = value.split(None, 1)
                    if len(setting_parts) == 2:
                        setting_name, setting_value = setting_parts
                        # Parse boolean values
                        if setting_value.lower() in ('true', 'false'):
                            config['settings'][setting_name] = setting_value.lower() == 'true'
                        else:
                            config['settings'][setting_name] = setting_value
        
        log(f"Loaded configuration from: {config_file}")
        return config
    except FileNotFoundError:
        log(f"WARNING: Config file '{config_file}' not found. Using defaults.")
        return None
    except Exception as e:
        log(f"WARNING: Error loading config file: {e}")
        return None

def setup_sdrplay_gains(sdr, config, use_agc):
    """Configure SDRplay-specific gain settings"""
    if use_agc:
        if sdr.hasGainMode(SOAPY_SDR_RX, 0):
            sdr.setGainMode(SOAPY_SDR_RX, 0, True)
        return
    
    gains = config.get('gains', {})
    ifgr = gains.get('IFGR', 23)
    rfgr = gains.get('RFGR', 0)
    
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, "IFGR", ifgr)
        sdr.setGain(SOAPY_SDR_RX, 0, "RFGR", rfgr)
        log(f"SDRplay gains: IFGR={ifgr}, RFGR={rfgr}")
    except Exception as e:
        log(f"Warning: Could not set IFGR/RFGR: {e}")
        # Fallback to combined gain
        combined_gain = 59 - ifgr  # Convert IFGR to positive gain
        sdr.setGain(SOAPY_SDR_RX, 0, combined_gain)
        log(f"Using combined gain: {combined_gain} dB")

def setup_rtlsdr_gains(sdr, config, use_agc):
    """Configure RTL-SDR gain settings"""
    if use_agc:
        try:
            sdr.setGainMode(SOAPY_SDR_RX, 0, True)
            log("RTL-SDR AGC: enabled")
        except:
            pass
        return
    
    gains = config.get('gains', {})
    gain = gains.get('TUNER', 40.0)
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, gain)
        log(f"RTL-SDR gain: {gain} dB")
    except Exception as e:
        log(f"Warning: Could not set gain: {e}")

def setup_airspy_gains(sdr, config, use_agc):
    """Configure Airspy gain settings"""
    if use_agc:
        try:
            sdr.setGainMode(SOAPY_SDR_RX, 0, True)
            log("Airspy AGC: enabled")
        except:
            pass
        return
    
    gains = config.get('gains', {})
    lna_gain = gains.get('LNA', 10)
    mixer_gain = gains.get('MIX', 10)
    vga_gain = gains.get('VGA', 10)
    
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, "LNA", lna_gain)
        sdr.setGain(SOAPY_SDR_RX, 0, "MIX", mixer_gain)
        sdr.setGain(SOAPY_SDR_RX, 0, "VGA", vga_gain)
        log(f"Airspy gains: LNA={lna_gain}, MIX={mixer_gain}, VGA={vga_gain}")
    except Exception as e:
        log(f"Warning: Could not set individual gains: {e}")

def setup_hackrf_gains(sdr, config, use_agc):
    """Configure HackRF gain settings"""
    gains = config.get('gains', {})
    settings = config.get('settings', {})
    lna_gain = gains.get('LNA', 16)
    vga_gain = gains.get('VGA', 20)
    amp = settings.get('amp', False)
    
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, "LNA", lna_gain)
        sdr.setGain(SOAPY_SDR_RX, 0, "VGA", vga_gain)
        sdr.setGain(SOAPY_SDR_RX, 0, "AMP", 1 if amp else 0)
        log(f"HackRF gains: LNA={lna_gain}, VGA={vga_gain}, AMP={'ON' if amp else 'OFF'}")
    except Exception as e:
        log(f"Warning: Could not set gains: {e}")

def setup_device_gains(sdr, device_type, config, use_agc):
    """Configure device-specific gain settings"""
    if device_type == 'sdrplay':
        setup_sdrplay_gains(sdr, config, use_agc)
    elif device_type == 'rtlsdr':
        setup_rtlsdr_gains(sdr, config, use_agc)
    elif device_type == 'airspy':
        setup_airspy_gains(sdr, config, use_agc)
    elif device_type == 'hackrf':
        setup_hackrf_gains(sdr, config, use_agc)
    else:
        # Generic gain setting for unknown devices
        if use_agc:
            try:
                sdr.setGainMode(SOAPY_SDR_RX, 0, True)
                log(f"{device_type} AGC: enabled")
            except:
                log(f"Warning: AGC not supported on {device_type}")
        else:
            gain = config.get('gain', 20.0)
            try:
                sdr.setGain(SOAPY_SDR_RX, 0, gain)
                log(f"{device_type} gain: {gain} dB")
            except Exception as e:
                log(f"Warning: Could not set gain: {e}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Stream IQ from any SoapySDR device to direwolf',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    
    parser.add_argument('--config', type=str, default='soapysdr.conf',
                        help='Configuration file (default: soapysdr.conf)')
    parser.add_argument('--device', type=str,
                        help='Device type: sdrplay, rtlsdr, airspy, hackrf, or auto')
    parser.add_argument('--freq', type=float,
                        help='Frequency in MHz (default: from config or 144.8)')
    parser.add_argument('--gain', type=float,
                        help='Gain in dB (device-specific)')
    parser.add_argument('--agc', action='store_true',
                        help='Enable automatic gain control')
    parser.add_argument('--list-devices', action='store_true',
                        help='List all available devices and exit')
    
    # SDRplay-specific
    parser.add_argument('--ifgr', type=int,
                        help='SDRplay IF Gain Reduction (20-59)')
    parser.add_argument('--rfgr', type=int,
                        help='SDRplay RF Gain Reduction (0-3)')
    
    # Airspy-specific
    parser.add_argument('--lna', type=int,
                        help='Airspy LNA gain (0-15)')
    parser.add_argument('--mixer', type=int,
                        help='Airspy Mixer gain (0-15)')
    parser.add_argument('--vga', type=int,
                        help='Airspy VGA gain (0-15)')
    
    args = parser.parse_args()
    
    # List devices and exit if requested
    if args.list_devices:
        list_devices()
        sys.exit(0)
    
    # Load configuration file
    config_data = load_config(args.config)
    
    # Determine device type
    device_type = args.device
    if not device_type:
        if config_data and config_data.get('device'):
            device_type = config_data['device']
        else:
            device_type = 'auto'
    
    # Auto-detect device if needed
    device_args = {}
    if device_type == 'auto':
        device_type, device_info = detect_device()
        # Use detected device info
        device_args = device_info
    elif isinstance(device_type, dict):
        # Device is already a dict from config
        device_args = device_type
        device_type = device_args.get('driver', 'unknown')
    else:
        device_args['driver'] = device_type
    
    # Get configuration for this device type
    device_config = {}
    if config_data:
        device_config = config_data.get(device_type, {})
        # Global settings
        frequency = (args.freq or config_data.get('frequency', 144.8)) * 1e6
        sample_rate = config_data.get('sample_rate', 192000)
    else:
        frequency = (args.freq or 144.8) * 1e6
        sample_rate = 192000
    
    # Override config with command-line arguments
    use_agc = args.agc or device_config.get('agc', False)
    
    if args.ifgr is not None:
        device_config['ifgr'] = args.ifgr
    if args.rfgr is not None:
        device_config['rfgr'] = args.rfgr
    if args.gain is not None:
        device_config['gain'] = args.gain
    if args.lna is not None:
        device_config['lna_gain'] = args.lna
    if args.mixer is not None:
        device_config['mixer_gain'] = args.mixer
    if args.vga is not None:
        device_config['vga_gain'] = args.vga
    
    log("=" * 60)
    log("SoapySDR to Direwolf IQ Streamer")
    log("=" * 60)
    log(f"Device: {device_type}")
    log(f"Frequency: {frequency/1e6} MHz")
    log(f"Sample rate: {sample_rate} Hz")
    log(f"AGC: {'ON' if use_agc else 'OFF'}")
    
    # Open device
    try:
        sdr = SoapySDR.Device(device_args)
    except Exception as e:
        log(f"ERROR: Could not open device: {e}")
        log("\nTry running with --list-devices to see available devices")
        sys.exit(1)
    
    # Configure device
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, frequency)
        
        # Set gains
        setup_device_gains(sdr, device_type, device_config, use_agc)
        
        # Log actual settings
        log(f"Actual sample rate: {sdr.getSampleRate(SOAPY_SDR_RX, 0)} Hz")
        log(f"Actual frequency: {sdr.getFrequency(SOAPY_SDR_RX, 0)/1e6} MHz")
        
        try:
            actual_gain = sdr.getGain(SOAPY_SDR_RX, 0)
            log(f"Actual gain: {actual_gain} dB")
        except:
            pass
        
    except Exception as e:
        log(f"ERROR: Could not configure device: {e}")
        sys.exit(1)
    
    # Setup stream
    try:
        rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rx_stream)
    except Exception as e:
        log(f"ERROR: Could not setup stream: {e}")
        sys.exit(1)
    
    log("=" * 60)
    log(f"Streaming IQ samples to stdout (CF32 @ {sample_rate} Hz)...")
    log("Pipe to: csdr fir_decimate_cc 8 | direwolf -M -t 0 -r 24000 -n 1 iq:24000")
    log("Press Ctrl+C to stop")
    log("=" * 60)
    
    # Buffer for receiving samples
    buff = np.zeros(4096, dtype=np.complex64)
    
    try:
        while True:
            # Read samples
            sr = sdr.readStream(rx_stream, [buff], len(buff))
            num_samples = sr.ret
            
            if num_samples > 0:
                # Write to stdout as interleaved float32 (I,Q,I,Q,...)
                iq_interleaved = np.empty(num_samples * 2, dtype=np.float32)
                iq_interleaved[0::2] = buff[:num_samples].real
                iq_interleaved[1::2] = buff[:num_samples].imag
                sys.stdout.buffer.write(iq_interleaved.tobytes())
                sys.stdout.buffer.flush()
    
    except KeyboardInterrupt:
        log("\nStopping...")
    
    except Exception as e:
        log(f"\nERROR: {e}")
    
    finally:
        try:
            sdr.deactivateStream(rx_stream)
            sdr.closeStream(rx_stream)
            log("Stream closed")
        except:
            pass

if __name__ == "__main__":
    main()
