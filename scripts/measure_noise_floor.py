#!/usr/bin/env python3
"""
Measure noise floor using the same pipeline as soapysdr_to_direwolf
RTL-SDR -> SoapySDR -> csdr decimate -> power measurement every 100ms
"""

import sys
import numpy as np
import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32
import subprocess
import struct
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
        'gains': {}
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
                        try:
                            config['gains'][gain_name.upper()] = float(gain_value)
                        except ValueError:
                            config['gains'][gain_name.upper()] = int(gain_value)
        
        return config
    except Exception as e:
        log(f"Error loading config: {e}")
        return config

def setup_rtlsdr(sdr, config):
    """Configure RTL-SDR"""
    use_agc = config['agc']
    
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
        log(f"RTL-SDR gain (TUNER): {gain} dB (requested {requested})")
    except Exception as e:
        log(f"Warning: Could not set gain: {e}")

def measure_power(config_file):
    """Measure power using same pipeline as soapysdr_to_direwolf"""
    
    config = load_config(config_file)
    
    log("=" * 60)
    log("Noise Floor Measurement Tool")
    log("=" * 60)
    log(f"Config file: {config_file}")
    log(f"Device: {config['device']}")
    log(f"Frequency: {config['frequency']} MHz")
    log(f"Sample rate: {config['sample_rate']} Hz")
    log(f"AGC: {'ON' if config['agc'] else 'OFF'}")
    
    # Calculate decimation (same as soapysdr_to_direwolf)
    decimation = max(1, int(config['sample_rate'] / 24000))
    output_rate = config['sample_rate'] // decimation
    
    log(f"Decimation: {decimation}")
    log(f"Output rate: {output_rate} Hz")
    log("=" * 60)
    
    # Open RTL-SDR
    try:
        sdr = SoapySDR.Device({'driver': 'rtlsdr'})
    except Exception as e:
        log(f"ERROR: Could not open RTL-SDR: {e}")
        sys.exit(1)
    
    # Configure device
    try:
        sdr.setSampleRate(SOAPY_SDR_RX, 0, config['sample_rate'])
        sdr.setFrequency(SOAPY_SDR_RX, 0, config['frequency'] * 1e6)
        setup_rtlsdr(sdr, config)
        
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
    
    # Start csdr decimation process (same as soapysdr_to_direwolf)
    csdr_cmd = ['csdr', 'fir_decimate_cc', str(decimation), '0.005', 'HAMMING']
    log(f"Starting decimation: {' '.join(csdr_cmd)}")
    
    try:
        csdr_process = subprocess.Popen(
            csdr_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    except FileNotFoundError:
        log("ERROR: csdr not found. Install with: sudo apt install csdr")
        sys.exit(1)
    
    log("=" * 60)
    log("Measuring power every 100ms... Press Ctrl+C to stop")
    log("=" * 60)
    log(f"{'Time (s)':<12} {'Power (dBFS)':<15} {'Status'}")
    log("-" * 60)
    
    buff = np.zeros(4096, dtype=np.complex64)
    measurement_count = 0
    start_time = time.time()
    
    # For power measurement
    samples_per_100ms = int(output_rate * 0.1)
    bytes_per_measurement = samples_per_100ms * 8  # CF32 = 8 bytes per sample
    accumulated_data = b''
    
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Use threading to read SDR and csdr output simultaneously
        import threading
        import queue
        
        sdr_queue = queue.Queue(maxsize=100)
        decimated_queue = queue.Queue(maxsize=100)
        
        def sdr_reader():
            while running:
                try:
                    sr = sdr.readStream(rx_stream, [buff], len(buff))
                    if sr.ret > 0:
                        # Copy the data
                        data = buff[:sr.ret].copy()
                        sdr_queue.put(data)
                except Exception as e:
                    if running:
                        log(f"SDR reader error: {e}")
                    break
        
        def csdr_writer():
            while running:
                try:
                    iq_samples = sdr_queue.get(timeout=1)
                    # Convert to interleaved float32 (CF32 format)
                    iq_interleaved = np.empty(len(iq_samples) * 2, dtype=np.float32)
                    iq_interleaved[0::2] = iq_samples.real
                    iq_interleaved[1::2] = iq_samples.imag
                    csdr_process.stdin.write(iq_interleaved.tobytes())
                    csdr_process.stdin.flush()
                except queue.Empty:
                    continue
                except (BrokenPipeError, ValueError):
                    break
        
        def csdr_reader():
            while running:
                try:
                    chunk = csdr_process.stdout.read(8192)
                    if chunk:
                        decimated_queue.put(chunk)
                    else:
                        time.sleep(0.001)
                except Exception as e:
                    if running:
                        log(f"CSDR reader error: {e}")
                    break
        
        # Start threads
        sdr_thread = threading.Thread(target=sdr_reader, daemon=True)
        writer_thread = threading.Thread(target=csdr_writer, daemon=True)
        reader_thread = threading.Thread(target=csdr_reader, daemon=True)
        
        sdr_thread.start()
        writer_thread.start()
        reader_thread.start()
        
        log("Threads started, waiting for data...")
        time.sleep(0.5)  # Let pipeline fill
        
        while running:
            # Get decimated data from queue
            try:
                chunk = decimated_queue.get(timeout=0.1)
                accumulated_data += chunk
            except queue.Empty:
                continue
            
            # Process complete measurements
            while len(accumulated_data) >= bytes_per_measurement:
                # Extract one measurement worth of data
                measurement_data = accumulated_data[:bytes_per_measurement]
                accumulated_data = accumulated_data[bytes_per_measurement:]
                
                # Parse CF32 data
                num_floats = len(measurement_data) // 4
                samples = struct.unpack(f'<{num_floats}f', measurement_data)
                
                # Convert to complex
                iq = np.array(samples, dtype=np.float32)
                iq_complex = iq[0::2] + 1j * iq[1::2]
                
                # Compute power in dBFS
                power = np.mean(np.abs(iq_complex)**2)
                if power > 0:
                    power_dbfs = 10 * np.log10(power)
                else:
                    power_dbfs = -100
                
                power_dbfs = max(-100, min(0, power_dbfs))
                
                elapsed = time.time() - start_time
                measurement_count += 1
                
                # Determine status (simple threshold)
                if power_dbfs > -35:
                    status = "SIGNAL"
                else:
                    status = "noise"
                
                print(f"{elapsed:<12.1f} {power_dbfs:<15.1f} {status}")
                sys.stdout.flush()
    
    except KeyboardInterrupt:
        pass
    
    except Exception as e:
        log(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        log("\nStopping...")
        try:
            sdr.deactivateStream(rx_stream)
            sdr.closeStream(rx_stream)
        except:
            pass
        
        try:
            csdr_process.terminate()
            csdr_process.wait(timeout=2)
        except:
            try:
                csdr_process.kill()
            except:
                pass
        
        elapsed = time.time() - start_time
        log(f"\nMeasurement summary:")
        log(f"  Duration: {elapsed:.1f} seconds")
        log(f"  Measurements: {measurement_count}")
        log(f"  Rate: {measurement_count/elapsed:.1f} measurements/sec")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 measure_noise_floor.py <config_file>")
        print("Example: python3 measure_noise_floor.py rtlsdr.conf")
        sys.exit(1)
    
    config_file = sys.argv[1]
    measure_power(config_file)
