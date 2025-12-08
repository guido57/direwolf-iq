#!/usr/bin/env python3
"""
Unified SoapySDR to Direwolf launcher with optional web interface.

This script provides two modes:
1. Direct streaming mode: Streams IQ samples from any SoapySDR device to stdout
2. Unified launcher mode: Runs a complete pipeline with optional web monitoring

Direct Streaming Mode (pipes to other tools):
  python3 soapysdr_to_direwolf.py --config rtlsdr.conf | csdr fir_decimate_cc 8 | direwolf

Unified Launcher Mode (command-line):
  python3 soapysdr_to_direwolf.py --config rtlsdr.conf --launcher
  python3 soapysdr_to_direwolf.py --config rsp1.conf --launcher --direwolf-config ~/direwolf.conf

Unified Launcher Mode (with web interface):
  python3 soapysdr_to_direwolf.py --config rsp1.conf --launcher --web
  # Then open http://localhost:5000 in your browser

Device-specific gain settings (direct mode only):
  SDRplay:  --ifgr 23 --rfgr 0
  RTL-SDR:  --gain 40.0
  Airspy:   --lna 10 --mixer 10 --vga 10
  HackRF:   --lna 16 --vga 20
"""

import sys
import argparse
import numpy as np
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

# Add scripts directory to path for imports
script_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(script_dir))

# ============================================================================
# SECTION 1: Direct Streaming Functions
# ============================================================================

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
    device_dict = dict(device_info)
    driver = device_dict.get('driver', 'unknown')
    log(f"Auto-detected device: {driver}")
    
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
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                
                key, value = parts[0].upper(), parts[1]
                
                if '#' in value:
                    value = value.split('#')[0].strip()
                else:
                    value = value.strip()
                
                if key == 'DEVICE':
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
                    gain_parts = value.split(None, 1)
                    if len(gain_parts) == 2:
                        gain_name, gain_value = gain_parts
                        try:
                            config['gains'][gain_name.upper()] = float(gain_value)
                        except ValueError:
                            config['gains'][gain_name.upper()] = int(gain_value)
                elif key == 'SETTING':
                    setting_parts = value.split(None, 1)
                    if len(setting_parts) == 2:
                        setting_name, setting_value = setting_parts
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
    
    # Explicitly disable AGC before setting manual gains
    try:
        if sdr.hasGainMode(SOAPY_SDR_RX, 0):
            sdr.setGainMode(SOAPY_SDR_RX, 0, False)
    except Exception as e:
        log(f"Warning: Could not disable SDRplay AGC: {e}")
    
    gains = config.get('gains', {})
    ifgr = gains.get('IFGR', 23)
    rfgr = gains.get('RFGR', 0)
    
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, "IFGR", ifgr)
        sdr.setGain(SOAPY_SDR_RX, 0, "RFGR", rfgr)
        log(f"SDRplay gains: IFGR={ifgr}, RFGR={rfgr}")
    except Exception as e:
        log(f"Warning: Could not set IFGR/RFGR: {e}")
        combined_gain = 59 - ifgr
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
    
    try:
        sdr.setGainMode(SOAPY_SDR_RX, 0, False)
        log("RTL-SDR AGC: disabled (manual gain)")
    except Exception as e:
        log(f"Warning: Could not disable RTL-SDR AGC: {e}")

    gains = config.get('gains', {})
    supported = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7,
                 16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8,
                 36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]
    requested = float(gains.get('TUNER', 40.0))
    requested = max(0.0, min(49.6, requested))
    gain = min(supported, key=lambda g: abs(g - requested))
    try:
        sdr.setGain(SOAPY_SDR_RX, 0, gain)
        log(f"RTL-SDR gain (TUNER snapped): {gain} dB (requested {requested})")
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

def run_direct_streaming(config_data, device_type, device_args, use_agc):
    """Run direct IQ streaming mode (outputs to stdout)"""
    if config_data:
        device_config = config_data
        frequency = config_data.get('frequency', 144.8) * 1e6
        sample_rate = config_data.get('sample_rate', 192000)
    else:
        device_config = {'gains': {}, 'settings': {}}
        frequency = 144.8 * 1e6
        sample_rate = 192000
    
    log("=" * 60)
    log("SoapySDR to Direwolf IQ Streamer")
    log("=" * 60)
    log(f"Device: {device_type}")
    log(f"Frequency: {frequency/1e6} MHz")
    log(f"Sample rate: {sample_rate} Hz")
    log(f"AGC: {'ON' if use_agc else 'OFF'}")
    
    try:
        sdr = SoapySDR.Device(device_args)
    except Exception as e:
        log(f"ERROR: Could not open device: {e}")
        log("\nTry running with --list-devices to see available devices")
        sys.exit(1)
    
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, sample_rate)
        sdr.setFrequency(SOAPY_SDR_RX, 0, frequency)
        setup_device_gains(sdr, device_type, device_config, use_agc)
        
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
    
    buff = np.zeros(4096, dtype=np.complex64)
    
    try:
        while True:
            sr = sdr.readStream(rx_stream, [buff], len(buff))
            num_samples = sr.ret
            
            if num_samples > 0:
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

# ============================================================================
# SECTION 2: Unified Launcher Functions
# ============================================================================

def find_config_file(config_name):
    """Find config file in scripts/ or current directory"""
    if os.path.exists(config_name):
        return config_name
    
    scripts_path = script_dir / config_name
    if scripts_path.exists():
        return str(scripts_path)
    
    if not config_name.endswith('.conf'):
        with_ext = f"{config_name}.conf"
        if os.path.exists(with_ext):
            return with_ext
        scripts_with_ext = script_dir / with_ext
        if scripts_with_ext.exists():
            return str(scripts_with_ext)
    
    return None

def find_direwolf_binary():
    """Find direwolf binary"""
    candidates = [
        './build/src/direwolf',
        '../build/src/direwolf',
        'direwolf',
    ]
    
    for candidate in candidates:
        try:
            result = subprocess.run([candidate, '-h'], 
                                    capture_output=True, 
                                    timeout=1)
            if result.returncode == 0 or result.returncode == 1:
                return candidate
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    
    return None

def start_pipeline(sdr_config, direwolf_config, direwolf_binary, use_web=False):
    """Start the SDR -> direwolf pipeline"""
    monitor_fifo = None
    if use_web:
        monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
        try:
            if os.path.exists(monitor_fifo):
                os.remove(monitor_fifo)
            os.mkfifo(monitor_fifo)
            print(f"Created monitoring FIFO: {monitor_fifo}")
        except Exception as e:
            print(f"Warning: couldn't create FIFO: {e}")
            monitor_fifo = None
    
    sample_rate = 192000
    try:
        with open(sdr_config, 'r') as f:
            for line in f:
                if line.strip().startswith('SAMPLE_RATE'):
                    sample_rate = int(line.split()[1])
                    break
    except:
        pass
    
    decimation = max(1, int(sample_rate / 24000))
    output_rate = sample_rate // decimation
    
    print(f"Pipeline configuration:")
    print(f"  SDR config: {sdr_config}")
    print(f"  Direwolf config: {direwolf_config}")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Decimation: {decimation}")
    print(f"  Output rate: {output_rate} Hz")
    print(f"  Web monitoring: {'enabled' if use_web else 'disabled'}")
    print()
    
    sdr_cmd = [sys.executable, str(script_dir / 'soapysdr_to_direwolf.py'), 
               '--config', sdr_config]
    
    print(f"Starting SDR: {' '.join(sdr_cmd)}")
    sdr_process = subprocess.Popen(sdr_cmd, stdout=subprocess.PIPE, stderr=sys.stderr)
    
    csdr_cmd = ['csdr', 'fir_decimate_cc', str(decimation), '0.005', 'HAMMING']
    print(f"Starting decimation: {' '.join(csdr_cmd)}")
    csdr_process = subprocess.Popen(csdr_cmd, stdin=sdr_process.stdout, 
                                     stdout=subprocess.PIPE, stderr=sys.stderr)
    sdr_process.stdout.close()
    
    if monitor_fifo:
        tee_cmd = ['tee', monitor_fifo]
        print(f"Starting tee: {' '.join(tee_cmd)}")
        tee_process = subprocess.Popen(tee_cmd, stdin=csdr_process.stdout,
                                        stdout=subprocess.PIPE, stderr=sys.stderr)
        csdr_process.stdout.close()
        direwolf_stdin = tee_process.stdout
    else:
        tee_process = None
        direwolf_stdin = csdr_process.stdout
    
    direwolf_cmd = [direwolf_binary, '-t', '0', '-r', str(output_rate), 
                    '-n', '1', f'iq:{output_rate}']
    
    if direwolf_config:
        direwolf_cmd.extend(['-c', direwolf_config])
    else:
        direwolf_cmd.append('-M')
    
    print(f"Starting direwolf: {' '.join(direwolf_cmd)}")
    
    if use_web:
        direwolf_process = subprocess.Popen(direwolf_cmd, stdin=direwolf_stdin,
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.STDOUT,
                                             text=True, bufsize=1)
    else:
        direwolf_process = subprocess.Popen(direwolf_cmd, stdin=direwolf_stdin,
                                             stdout=sys.stdout, stderr=sys.stderr)
    
    if tee_process:
        direwolf_stdin.close()
        return (sdr_process, csdr_process, tee_process, direwolf_process, monitor_fifo)
    else:
        csdr_process.stdout.close()
        return (sdr_process, csdr_process, None, direwolf_process, monitor_fifo)

def cleanup_pipeline(processes, monitor_fifo):
    """Clean up pipeline processes and FIFO"""
    print("\nStopping pipeline...")
    
    for process in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            except:
                pass
    
    if monitor_fifo and os.path.exists(monitor_fifo):
        try:
            os.remove(monitor_fifo)
            print(f"Removed monitoring FIFO: {monitor_fifo}")
        except:
            pass

def run_web_interface(sdr_config_path, direwolf_config, direwolf_binary, pipeline_processes, monitor_fifo):
    """Run the web interface in a separate thread"""
    from flask import Flask, render_template, jsonify, request
    from flask_socketio import SocketIO
    import web_interface
    
    direwolf_process = pipeline_processes[-1]
    
    web_interface.pipeline_process = direwolf_process
    web_interface.pipeline_running = True
    
    print("Starting pipeline reader thread for packet parsing...")
    reader_thread = threading.Thread(
        target=web_interface.pipeline_reader, 
        args=(direwolf_process,),
        daemon=True
    )
    reader_thread.start()
    print("Pipeline reader thread started")
    
    original_start = web_interface.start_pipeline
    original_stop = web_interface.stop_pipeline
    
    # Store references to processes in the closure
    current_processes = {'processes': pipeline_processes, 'fifo': monitor_fifo}
    
    def custom_start():
        """Restart pipeline with updated config from web interface"""
        nonlocal current_processes, sdr_config_path
        
        print("Restarting pipeline with new configuration...")
        
        # Stop current pipeline
        cleanup_pipeline(current_processes['processes'], current_processes['fifo'])
        web_interface.pipeline_running = False
        # Wait for RSSI monitor to detect FIFO removal and close it
        time.sleep(2)
        
        try:
            # Regenerate SoapySDR config from current web settings
            new_sdr_config = web_interface.generate_soapysdr_config()
            sdr_config_path = new_sdr_config

            # Restart pipeline with freshly generated config
            pipeline_result = start_pipeline(new_sdr_config, direwolf_config, 
                                           direwolf_binary, use_web=True)
            
            if len(pipeline_result) == 5:
                sdr_proc, csdr_proc, tee_proc, dw_proc, fifo = pipeline_result
                processes = [p for p in [sdr_proc, csdr_proc, tee_proc, dw_proc] if p]
                current_processes = {'processes': processes, 'fifo': fifo}
                
                # Update references
                web_interface.pipeline_process = dw_proc
                web_interface.pipeline_running = True
                
                # Restart reader thread
                reader_thread = threading.Thread(
                    target=web_interface.pipeline_reader, 
                    args=(dw_proc,),
                    daemon=True
                )
                reader_thread.start()
                
                print("Pipeline restarted successfully")
                return {'success': True}
            else:
                return {'success': False, 'error': 'Failed to start pipeline'}
                
        except Exception as e:
            print(f"Error restarting pipeline: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def custom_stop():
        cleanup_pipeline(current_processes['processes'], current_processes['fifo'])
        web_interface.pipeline_running = False
        return {'success': True}
    
    web_interface.start_pipeline = custom_start
    web_interface.stop_pipeline = custom_stop
    
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger('werkzeug').disabled = True
    logging.getLogger('socketio').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.ERROR)
    
    print("\n" + "=" * 80)
    print("Starting Web Interface...")
    print("Open http://localhost:5000 in your browser")
    print("=" * 80)
    
    web_interface.socketio.run(web_interface.app, host='0.0.0.0', port=5000, 
                                debug=False, log_output=False, 
                                allow_unsafe_werkzeug=True)

def run_unified_launcher(args):
    """Run the unified launcher mode"""
    if not args.config:
        print("ERROR: --config is required for launcher mode (or use --web --no-autostart for manual mode)")
        sys.exit(1)
    
    sdr_config = find_config_file(args.config)
    if not sdr_config:
        print(f"ERROR: Could not find config file: {args.config}")
        print("\nAvailable configs in scripts/:")
        for conf_file in script_dir.glob('*.conf'):
            print(f"  {conf_file.name}")
        sys.exit(1)
    
    direwolf_binary = find_direwolf_binary()
    if not direwolf_binary:
        print("ERROR: Could not find direwolf binary")
        print("Tried: ./build/src/direwolf, ../build/src/direwolf, direwolf (in PATH)")
        sys.exit(1)
    
    direwolf_config = args.direwolf_config
    if direwolf_config and not os.path.exists(direwolf_config):
        print(f"ERROR: Direwolf config not found: {direwolf_config}")
        sys.exit(1)
    
    pipeline_result = start_pipeline(sdr_config, direwolf_config, 
                                      direwolf_binary, use_web=args.web)
    
    if args.web and len(pipeline_result) == 5:
        sdr_proc, csdr_proc, tee_proc, dw_proc, fifo = pipeline_result
        processes = [p for p in [sdr_proc, csdr_proc, tee_proc, dw_proc] if p]
        
        import web_interface
        monitor_thread = threading.Thread(target=web_interface.continuous_rssi_monitor, 
                                          daemon=True)
        monitor_thread.start()
        
        time.sleep(2)
        
        def signal_handler(sig, frame):
            cleanup_pipeline(processes, fifo)
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            run_web_interface(sdr_config, direwolf_config, direwolf_binary, processes, fifo)
        except KeyboardInterrupt:
            pass
        finally:
            cleanup_pipeline(processes, fifo)
    
    else:
        if len(pipeline_result) == 5:
            sdr_proc, csdr_proc, tee_proc, dw_proc, fifo = pipeline_result
            processes = [p for p in [sdr_proc, csdr_proc, tee_proc, dw_proc] if p]
        else:
            sdr_proc, csdr_proc, tee_proc, dw_proc, fifo = (*pipeline_result, None, None, None)
            processes = [p for p in [sdr_proc, csdr_proc, tee_proc, dw_proc] if p]
        
        def signal_handler(sig, frame):
            cleanup_pipeline(processes, fifo)
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("\nPipeline running. Press Ctrl+C to stop.")
        
        try:
            dw_proc.wait()
        except KeyboardInterrupt:
            pass
        finally:
            cleanup_pipeline(processes, fifo)

# ============================================================================
# SECTION 3: Main Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Unified SoapySDR to Direwolf launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    
    # Direct streaming mode options
    parser.add_argument('--config', type=str, default='soapysdr.conf',
                        help='Configuration file or device type')
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
    
    # Device-specific options
    parser.add_argument('--ifgr', type=int,
                        help='SDRplay IF Gain Reduction (20-59)')
    parser.add_argument('--rfgr', type=int,
                        help='SDRplay RF Gain Reduction (0-3)')
    parser.add_argument('--lna', type=int,
                        help='Airspy LNA gain (0-15)')
    parser.add_argument('--mixer', type=int,
                        help='Airspy Mixer gain (0-15)')
    parser.add_argument('--vga', type=int,
                        help='Airspy VGA gain (0-15)')
    
    # Unified launcher options
    parser.add_argument('--launcher', action='store_true',
                        help='Enable unified launcher mode with optional web interface')
    parser.add_argument('--direwolf-config', '-d', type=str,
                        help='Direwolf config file (for launcher mode)')
    parser.add_argument('--web', '-w', action='store_true',
                        help='Enable web interface for monitoring (launcher mode)')
    parser.add_argument('--no-autostart', action='store_true',
                        help='With --web, start web interface without auto-starting pipeline')
    parser.add_argument('--list-configs', action='store_true',
                        help='List available config files and exit')
    
    args = parser.parse_args()
    
    # List devices
    if args.list_devices:
        list_devices()
        sys.exit(0)
    
    # List configs
    if args.list_configs:
        print("Available SDR config files:")
        for conf_file in script_dir.glob('*.conf'):
            print(f"  {conf_file.name}")
        sys.exit(0)
    
    # Web-only mode (launcher)
    if args.web and args.no_autostart:
        import web_interface
        print("Starting in web-only mode (no pipeline auto-start)")
        print("=" * 80)
        print("Web Interface - Manual Mode")
        print("Open http://localhost:5000 in your browser")
        print("Use the UI to configure and start the pipeline")
        print("=" * 80)
        web_interface.socketio.run(web_interface.app, host='0.0.0.0', port=5000,
                                    debug=False, log_output=False,
                                    allow_unsafe_werkzeug=True)
        return
    
    # Unified launcher mode
    if args.launcher or args.web or args.direwolf_config:
        run_unified_launcher(args)
        return
    
    # Direct streaming mode (default)
    config_data = load_config(args.config)
    
    device_type = args.device
    if not device_type:
        if config_data and config_data.get('device'):
            device_type = config_data['device']
        else:
            device_type = 'auto'
    
    device_args = {}
    if device_type == 'auto':
        device_type, device_info = detect_device()
        device_args = device_info
    elif isinstance(device_type, dict):
        device_args = device_type
        device_type = device_args.get('driver', 'unknown')
    else:
        device_args['driver'] = device_type
    
    if config_data:
        device_config = config_data
        if args.freq:
            config_data['frequency'] = args.freq
        if args.ifgr is not None:
            config_data['gains']['IFGR'] = args.ifgr
        if args.rfgr is not None:
            config_data['gains']['RFGR'] = args.rfgr
        if args.gain is not None:
            config_data['gains']['TUNER'] = args.gain
    else:
        device_config = {'gains': {}, 'settings': {}}
    
    use_agc = args.agc or (config_data and config_data.get('agc', False))
    
    run_direct_streaming(device_config, device_type, device_args, use_agc)

if __name__ == "__main__":
    main()
