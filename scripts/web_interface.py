#!/usr/bin/env python3
"""
Flask web interface for Direwolf SDR monitoring and control.
Features:
- Real-time packet display with RSSI/SNR metrics
- Control buttons for gain/frequency adjustment
- Live RSSI/SNR charts
- Station list with direct/digipeated indicators
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import subprocess
import threading
import re
import json
import time
import os
import logging
import sys
from datetime import datetime
from collections import defaultdict, deque

app = Flask(__name__)
app.config['SECRET_KEY'] = 'direwolf-sdr-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# File-based logger so errors don't get lost in console scroll
LOG_FILE = os.path.join(os.path.dirname(__file__), 'direwolf_iq.log')
logger = logging.getLogger('direwolf_iq')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    _handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    _formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)

# Global state
pipeline_process = None
pipeline_running = False
pipeline_lock = threading.Lock()

# Background monitor thread state. When this module is imported by a WSGI/Flask
# runner (e.g., `flask run`, gunicorn), the `__main__` block won't execute.
# Start the RSSI monitor lazily on first use so the UI keeps working.
_monitor_thread = None
_monitor_lock = threading.Lock()

# Configuration
# Now uses SoapySDR config files for multi-device support
# Use ~24 kHz IQ into Direwolf; extra Python FIR can narrow to 12/8/6/4 kHz.
TARGET_OUTPUT_RATE = 24000  # Desired Direwolf input rate in Hz
config = {
    'device': 'rtlsdr',  # Device type: 'rtlsdr', 'sdrplay', 'airspy', 'hackrf'
    'frequency': 144.8,  # 2m APRS frequency
    'sample_rate': 1024000,  # RTL-SDR: 1.024M, SDRplay: 192k
    'gain': 40.0,  # Generic gain (for backward compatibility)
    'ifgr': 40,      # Gain for RTL-SDR (0-50) or SDRplay IFGR (20-59)
    'rfgr': 0,       # SDRplay RF Gain Reduction (0-3)
    'agc': False,
    # Interpreted as channel bandwidth selector for Python FIR: '24k','12k','8k','6k','4k'
    'filter_quality': '24k',
    'decimation': 64,  # Calculated based on sample rate
    'color_output': True  # Colorize console output
}

# Statistics
stats = {
    'packets_received': 0,
    'stations_heard': set(),
    'direct_rf_senders': set(),
    'last_packets': deque(maxlen=500),  # Store up to 500 recent packets
    'rssi_history': deque(maxlen=100),
    'snr_history': deque(maxlen=100),
    'continuous_rssi': deque(maxlen=600),  # 60 seconds at 100ms (10 samples/sec)
    'last_audio_level': 0,
    # station_list structure:
    # callsign: {
    #   'direct': {'count', 'last_seen', 'rssi', 'snr'},
    #   'via': { digipeater: {'count', 'last_seen', 'rssi', 'snr'} }
    # }
    'station_list': {}
}

def parse_direwolf_line(line):
    """Parse direwolf output line for packet info.
    Accepts lines with or without trailing [RSSI=..., SNR=...] metrics.
    """
    # Common example with metrics:
    #   [0.2] CALLSIGN>DEST,PATH*:payload [RSSI=-28.1 dBFS (S9+19), SNR=32.0 dB]
    # And without metrics:
    #   [0.2] CALLSIGN>DEST,PATH*:payload
    
    # Try to capture sender, path and message regardless of metrics presence
    packet_match = re.search(r'\[[\d.]+\]\s+([^>]+)>([^:]+):(.*?)(?:\s*\[RSSI=|$)', line)
    metric_match = re.search(r'\[RSSI=([\-\d.]+)\s+dBFS.*?SNR=([\d.]+)\s+dB\]', line)
    
    if not packet_match:
        # Fallback: lines without leading timestamp bracket
        packet_match = re.search(r'^\s*([^>]+)>([^:]+):(.*)$', line)
        if not packet_match:
            return None
    
    sender = packet_match.group(1)
    path = packet_match.group(2)
    message = packet_match.group(3)
    
    # Determine if direct transmission by checking for asterisk in path
    # Asterisk (*) after a callsign means it was digipeated through that station
    # No asterisk = direct reception (not digipeated)
    path_parts = path.split(',')
    direct = True  # Assume direct unless we find an asterisk
    last_digipeater = "Direct"
    
    # Check if there's any asterisk in the path
    for part in path_parts:
        if '*' in part:
            direct = False
            callsign = part.replace('*', '').strip()
            # If it's WIDE*, find the last real callsign before it
            if callsign.startswith('WIDE'):
                # Look backwards from this position to find last real callsign
                idx = path_parts.index(part)
                for i in range(idx - 1, 0, -1):  # Skip index 0 (destination)
                    prev_call = path_parts[i].replace('*', '').strip()
                    # Real callsign = not WIDE and not just a destination like APMI04
                    if not prev_call.startswith('WIDE') and not prev_call.startswith('AP'):
                        last_digipeater = prev_call
                        break
            else:
                # It's a real callsign with asterisk (like IR5AE*), use it directly
                last_digipeater = callsign
    
    rssi = None
    snr = None
    if metric_match:
        rssi = float(metric_match.group(1))
        snr = float(metric_match.group(2))
    
    return {
        'timestamp': datetime.now().isoformat(),
        'sender': sender,
        'path': path,
        'message': message[:100],  # Truncate long messages
        'rssi': rssi,
        'snr': snr,
        'direct': direct,
        'last_digipeater': last_digipeater
    }

def parse_audio_level(line):
    """Parse direwolf audio level output for continuous monitoring."""
    # Example: "IW5ALZ-12 audio level = 61(6/6)    ||||||___"
    # Also: "Digipeater IR5AE audio level = 155(9/9)"
    match = re.search(r'audio level = (\d+)', line)
    if match:
        return int(match.group(1))
    return None

# Simple ANSI colorizer for console output when Direwolf is piped
ANSI = {
    'reset': "\x1b[0m",
    'red': "\x1b[31m",
    'yellow': "\x1b[33m",
    'green': "\x1b[32m",
    'cyan': "\x1b[36m",
    'blue': "\x1b[34m",
    'dim': "\x1b[2m",
}

def colorize_console_line(line, packet=None, audio_level=None):
    if not config.get('color_output', True):
        return line
    lo = line.lower()
    color = None
    if 'error' in lo:
        color = 'red'
    elif 'warning' in lo or 'obsolete' in lo:
        color = 'yellow'
    elif audio_level is not None or 'audio level' in lo:
        color = 'blue'
    elif packet is not None:
        color = 'green'
    elif any(k in lo for k in ['starting', 'device:', 'sample rate', 'iq input mode', 'fm demodulator']):
        color = 'cyan'
    if color:
        return f"{ANSI[color]}{line}{ANSI['reset']}"
    return line

def generate_soapysdr_config():
    """Generate a temporary SoapySDR config file from current settings."""
    config_path = '/tmp/web_interface_sdr.conf'
    
    # Determine sample rate decimation for output (informational only)
    # After decimation, we target ~8 kHz output
    decimation = max(1, int(config['sample_rate'] / TARGET_OUTPUT_RATE))
    
    # Build config content
    config_content = f"""# Auto-generated config for web interface
DEVICE driver={config['device']}
FREQUENCY {config['frequency']}
SAMPLE_RATE {config['sample_rate']}
AGC {str(config['agc']).lower()}
"""
    
    # Add device-specific gain parameter
    if config['device'] == 'rtlsdr':
        # RTL-SDR uses discrete TUNER gains; snap to closest supported value
        supported = [0.0, 0.9, 1.4, 2.7, 3.7, 7.7, 8.7, 12.5, 14.4, 15.7,
                     16.6, 19.7, 20.7, 22.9, 25.4, 28.0, 29.7, 32.8, 33.8,
                     36.4, 37.2, 38.6, 40.2, 42.1, 43.4, 43.9, 44.5, 48.0, 49.6]
        requested = max(0.0, min(50.0, float(config['ifgr'])))
        gain = min(supported, key=lambda g: abs(g - requested))
        config_content += f"GAIN TUNER {gain}\n"
    elif config['device'] == 'sdrplay':
        # SDRplay uses IFGR (IF Gain Reduction) and RFGR (RF Gain Reduction)
        ifgr = max(20, min(59, int(config['ifgr'])))
        rfgr = max(0, min(3, int(config['rfgr'])))
        config_content += f"GAIN IFGR {ifgr}\nGAIN RFGR {rfgr}\n"
    elif config['device'] == 'airspy':
        config_content += f"GAIN LINEARITY {config['gain']}\n"
    elif config['device'] == 'hackrf':
        config_content += f"GAIN LNA {config['gain']}\n"
    
    # Write config file
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    return config_path

def enhance_packet_with_peak_rssi(packet):
    """Replace direwolf's RSSI with peak value from continuous monitoring."""
    global stats
    
    if not packet or not packet.get('timestamp'):
        return packet
    
    continuous = list(stats['continuous_rssi'])
    if len(continuous) < 2:
        return packet  # Not enough data yet
    
    try:
        packet_time = datetime.fromisoformat(packet['timestamp'])
    except:
        return packet
    
    # Find closest sample to packet timestamp
    min_delta = float('inf')
    center_idx = -1
    
    for i, sample in enumerate(continuous):
        try:
            sample_time = datetime.fromisoformat(sample['time'])
            delta = abs((sample_time - packet_time).total_seconds())
            if delta < min_delta:
                min_delta = delta
                center_idx = i
        except:
            continue
    
    # Require match within 500ms
    if center_idx == -1 or min_delta > 0.5:
        return packet
    
    # Search for peak in ±500ms window (~5 samples at 100ms)
    window_size = 5
    start_idx = max(0, center_idx - window_size)
    end_idx = min(len(continuous) - 1, center_idx + window_size)
    
    peak_rssi = continuous[center_idx]['value']
    for i in range(start_idx, end_idx + 1):
        if continuous[i]['value'] > peak_rssi:
            peak_rssi = continuous[i]['value']
    
    # Replace RSSI with peak value
    # SNR can be approximated as: peak_rssi - noise_floor
    # Estimate noise floor from the minimum in a wider window
    noise_window = 20  # ~2 seconds
    noise_start = max(0, center_idx - noise_window)
    noise_end = min(len(continuous) - 1, center_idx + noise_window)
    
    noise_floor = min(continuous[i]['value'] for i in range(noise_start, noise_end + 1))
    estimated_snr = peak_rssi - noise_floor
    
    packet['rssi'] = peak_rssi
    packet['snr'] = estimated_snr
    
    return packet

def pipeline_reader(process):
    """Read direwolf output and update statistics."""
    global stats
    logger.info("pipeline_reader: started")

    for raw_line in iter(process.stdout.readline, ''):
        if not raw_line:
            break
        try:
            line = raw_line.strip()

            # Log every Direwolf line to file, with basic severity guess
            lo = line.lower()
            if 'error' in lo or 'exception' in lo:
                logger.error(line)
            elif 'warning' in lo:
                logger.warning(line)
            else:
                logger.info(line)

            # Parse audio level and packet before printing so we can colorize
            audio_level = parse_audio_level(line)
            if audio_level is not None:
                stats['last_audio_level'] = audio_level
            packet = parse_direwolf_line(line)

            # Print direwolf output to console with optional colors
            print(colorize_console_line(line, packet=packet, audio_level=audio_level))
            
            if packet:
                # Enhance packet with peak RSSI/SNR from continuous monitoring
                packet = enhance_packet_with_peak_rssi(packet)
                
                stats['packets_received'] += 1
                stats['last_packets'].append(packet)
                
                sender = packet['sender']
                
                stats['stations_heard'].add(sender)
                
                if packet['direct']:
                    stats['direct_rf_senders'].add(sender)
                
                # Initialize station entry if needed
                if sender not in stats['station_list']:
                    stats['station_list'][sender] = {
                        'first_seen': packet['timestamp'],
                        'direct': {'count': 0, 'last_seen': None, 'rssi': None, 'snr': None},
                        'via': {}
                    }

                # Update direct or via-digipeater bucket
                if packet['direct']:
                    bucket = stats['station_list'][sender]['direct']
                else:
                    digi = packet['last_digipeater'] or 'Unknown'
                    if digi not in stats['station_list'][sender]['via']:
                        stats['station_list'][sender]['via'][digi] = {
                            'count': 0,
                            'last_seen': None,
                            'rssi': None,
                            'snr': None
                        }
                    bucket = stats['station_list'][sender]['via'][digi]

                bucket['count'] = bucket['count'] + 1
                bucket['last_seen'] = packet['timestamp']
                bucket['rssi'] = packet['rssi']
                bucket['snr'] = packet['snr']
                
                # Update metrics history
                if packet['rssi'] is not None:
                    stats['rssi_history'].append({
                        'time': packet['timestamp'],
                        'value': packet['rssi'],
                        'station': sender
                    })
                
                if packet['snr'] is not None:
                    stats['snr_history'].append({
                        'time': packet['timestamp'],
                        'value': packet['snr'],
                        'station': sender
                    })
                
                # Emit to connected clients
                socketio.emit('new_packet', packet)
                socketio.emit('stats_update', get_stats())
        except Exception:
            logger.exception("pipeline_reader: error while processing line")

    # If the pipeline process ended, reflect that in state.
    try:
        rc = process.poll()
    except Exception:
        rc = None

    if rc is not None:
        logger.warning(f"pipeline_reader: pipeline process exited with code {rc}")
        with pipeline_lock:
            # Only flip the flag if nothing else already stopped it.
            global pipeline_running, pipeline_process
            if pipeline_process is process:
                pipeline_process = None
            pipeline_running = False
        try:
            socketio.emit('stats_update', get_stats())
        except Exception:
            logger.exception("pipeline_reader: error emitting final stats_update")

    logger.info("pipeline_reader: stopped")

# Signal power monitoring using tee to tap the pipeline
def continuous_rssi_monitor():
    """Background thread to compute RSSI every 100ms by tapping IQ stream."""
    global stats, pipeline_running, config
    
    import numpy as np
    import struct
    
    monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'

    # Rate-limit noisy diagnostics but keep enough breadcrumbs to understand
    # FIFO writer/reader behavior over long runtimes.
    last_diag = 0.0
    bytes_total = 0
    last_open_log = 0.0
    
    keepalive_fd = None
    while True:
        if pipeline_running:
            try:
                # Check if FIFO exists
                if not os.path.exists(monitor_fifo):
                    # FIFO not yet created; wait quietly
                    time.sleep(0.5)
                    continue

                # Open a persistent keepalive read handle so writers never see zero readers
                if keepalive_fd is None:
                    try:
                        keepalive_fd = os.open(monitor_fifo, os.O_RDONLY | os.O_NONBLOCK)
                        # Do not read from keepalive_fd; it's only to prevent writer EPIPE
                        now = time.time()
                        if now - last_open_log > 5:
                            logger.info(f"RSSI monitor: keepalive reader opened on FIFO {monitor_fifo}")
                            last_open_log = now
                    except Exception as e:
                        # Only report actual errors
                        logger.warning(f"RSSI monitor: keepalive open failed: {e}")
                
                # Calculate output rate after decimation (match main pipeline, ~24 kHz)
                decimation = max(1, int(config['sample_rate'] / TARGET_OUTPUT_RATE))
                output_rate = config['sample_rate'] // decimation
                
                fifo = None
                try:
                    # Open FIFO with non-blocking mode first to avoid hanging
                    fd = os.open(monitor_fifo, os.O_RDONLY | os.O_NONBLOCK)
                    # Switch back to blocking mode for actual reads
                    import fcntl
                    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
                    # Convert to regular file object
                    fifo = os.fdopen(fd, 'rb')

                    now = time.time()
                    if now - last_open_log > 5:
                        logger.info(f"RSSI monitor: FIFO reader opened (blocking) on {monitor_fifo}")
                        last_open_log = now

                    # Buffer reads to avoid spurious EOF/incomplete chunks
                    buf = bytearray()
                    while pipeline_running:
                        # Check if FIFO still exists (might be deleted during restart)
                        if not os.path.exists(monitor_fifo):
                            logger.info("RSSI monitor: FIFO removed, reopening...")
                            break

                        # Read 100ms of IQ data: output_rate * 0.1s samples * 8 bytes (CF32)
                        samples_per_100ms = int(output_rate * 0.1)
                        chunk_size = samples_per_100ms * 8

                        # Fill buffer until we have a full chunk or hit EOF
                        while len(buf) < chunk_size and pipeline_running:
                            data = fifo.read(chunk_size - len(buf))
                            if data is None:
                                # Should not happen with blocking reads, yield briefly
                                time.sleep(0.01)
                                continue
                            if len(data) == 0:
                                # True EOF – likely pipeline restart; reopen outer loop
                                now = time.time()
                                if now - last_diag > 1:
                                    logger.info("RSSI monitor: FIFO EOF (writer likely restarted), reopening")
                                    last_diag = now
                                break
                            bytes_total += len(data)
                            buf.extend(data)

                        if len(buf) < chunk_size:
                            # Not enough data to process; reopen FIFO
                            break

                        chunk = bytes(buf[:chunk_size])
                        del buf[:chunk_size]

                        # Parse CF32 (float32 I, float32 Q interleaved)
                        num_floats = len(chunk) // 4
                        samples = struct.unpack(f'<{num_floats}f', chunk)

                        # Convert to complex
                        iq = np.array(samples, dtype=np.float32)
                        iq_complex = iq[0::2] + 1j * iq[1::2]

                        # Compute power in dBFS
                        power = np.mean(np.abs(iq_complex)**2)
                        rssi_dbfs = 10 * np.log10(power) if power > 0 else -100
                        rssi_dbfs = max(-100, min(0, rssi_dbfs))

                        timestamp = datetime.now().isoformat()
                        stats['continuous_rssi'].append({
                            'time': timestamp,
                            'value': rssi_dbfs
                        })

                        # Emit to clients; errors here should not stop FIFO draining
                        try:
                            socketio.emit('continuous_rssi', {
                                'time': timestamp,
                                'value': rssi_dbfs
                            })
                        except Exception:
                            logger.exception("RSSI monitor: error emitting continuous_rssi")

                        # Periodic diagnostic to prove data is flowing end-to-end
                        now = time.time()
                        if now - last_diag > 30:
                            logger.info(
                                "RSSI monitor: flowing IQ via FIFO "
                                f"(rate~{output_rate}Hz, chunk={chunk_size}B/100ms, bytes_total={bytes_total}, last_rssi={rssi_dbfs:.1f} dBFS)"
                            )
                            last_diag = now
                finally:
                    if fifo is not None:
                        try:
                            fifo.close()
                        except Exception:
                            pass
                # Do not close keepalive_fd here; it stays open to keep writer alive
                        
            except FileNotFoundError:
                # FIFO not available yet; wait quietly
                time.sleep(1)
            except Exception:
                logger.exception("RSSI monitor: unexpected error")
                time.sleep(1)
        else:
            # Pipeline stopped: cleanup keepalive handle if present
            if keepalive_fd is not None:
                try:
                    os.close(keepalive_fd)
                except Exception:
                    pass
                keepalive_fd = None
            time.sleep(0.5)

def ensure_continuous_rssi_monitor_started():
    """Start the continuous RSSI monitor thread once.

    This must not rely on the `__main__` block because many deployment modes
    import this module without executing it.
    """
    global _monitor_thread
    with _monitor_lock:
        if _monitor_thread is not None and _monitor_thread.is_alive():
            return
        _monitor_thread = threading.Thread(target=continuous_rssi_monitor, daemon=True)
        _monitor_thread.start()
        logger.info("RSSI monitor: background thread started")

def start_pipeline():
    """Start the SDR→direwolf pipeline with IQ tapping for continuous RSSI."""
    global pipeline_process, pipeline_running
    
    with pipeline_lock:
        if pipeline_running and pipeline_process:
            return {'success': False, 'error': 'Pipeline already running'}
        
        # Ensure clean state
        if pipeline_process is not None:
            try:
                pipeline_process.kill()
                pipeline_process.wait(timeout=2)
            except:
                pass
            pipeline_process = None
        
        pipeline_running = False
        
        try:
            # Create named pipe for monitoring
            monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
            try:
                if os.path.exists(monitor_fifo):
                    os.remove(monitor_fifo)
                os.mkfifo(monitor_fifo)
                print(f"Created monitoring FIFO: {monitor_fifo}")
                logger.info(f"Pipeline: created monitoring FIFO {monitor_fifo}")
            except Exception as e:
                print(f"Warning: couldn't create FIFO: {e}")
                logger.warning(f"Pipeline: couldn't create monitoring FIFO {monitor_fifo}: {e}")
            
            # Generate SoapySDR config file
            sdr_config = generate_soapysdr_config()
            print(f"Generated SoapySDR config: {sdr_config}")
            
            # Calculate decimation and output rate (target ~6 kHz)
            decimation = max(1, int(config['sample_rate'] / TARGET_OUTPUT_RATE))
            output_rate = config['sample_rate'] // decimation
            
            # Build command with generic SoapySDR interface
            filter_arg = f"{decimation} 0.005 HAMMING" if config['filter_quality'] == 'high' else str(decimation)
            
            # Use soapysdr_to_direwolf.py for multi-device support
            sdr_cmd = f"python3 scripts/soapysdr_to_direwolf.py --config {sdr_config}"
            
            # Add tee after decimation (at direwolf input) for accurate RSSI measurement
            # Prefer repo direwolf config to avoid default search failures
            dw_conf = os.path.join(os.getcwd(), 'conf', 'sdr.conf')
            dw_conf_arg = f"-c {dw_conf}" if os.path.exists(dw_conf) else ""
            if not dw_conf_arg:
                print("WARNING: conf/sdr.conf not found; Direwolf will use defaults.")

            full_cmd = (
                f"{sdr_cmd} 2>/dev/null | "
                f"csdr fir_decimate_cc {filter_arg} 2>/dev/null | "
                f"tee {monitor_fifo} | "
                f"./build/src/direwolf {dw_conf_arg} -M -t 0 -r {output_rate} -n 1 iq:{output_rate} 2>&1"
            )
            
            print(f"Starting pipeline with command: {full_cmd}")
            print(f"Config: device={config['device']}, freq={config['frequency']}, sample_rate={config['sample_rate']}, decimation={decimation}")
            
            cmd = ['bash', '-c', full_cmd]
            
            pipeline_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='latin-1',
                errors='replace',
                bufsize=1
            )
            
            pipeline_running = True
            
            # Start reader thread
            reader_thread = threading.Thread(target=pipeline_reader, args=(pipeline_process,))
            reader_thread.daemon = True
            reader_thread.start()
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

def stop_pipeline():
    """Stop the SDR→direwolf pipeline."""
    global pipeline_process, pipeline_running
    
    with pipeline_lock:
        if not pipeline_running:
            return {'success': False, 'error': 'Pipeline not running'}
        
        try:
            if pipeline_process:
                # Try graceful termination first
                pipeline_process.terminate()
                try:
                    pipeline_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if terminate didn't work
                    print("Pipeline didn't terminate gracefully, forcing kill...")
                    pipeline_process.kill()
                    pipeline_process.wait(timeout=2)
                
                pipeline_process = None
            
            pipeline_running = False
            
            # Give time for threads to finish reading
            time.sleep(0.5)
            
            # Clean up monitoring FIFO
            monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
            import os
            try:
                if os.path.exists(monitor_fifo):
                    os.remove(monitor_fifo)
                    print(f"Removed monitoring FIFO: {monitor_fifo}")
                    logger.info(f"Pipeline: removed monitoring FIFO {monitor_fifo}")
            except Exception as e:
                print(f"Warning: couldn't remove FIFO: {e}")
                logger.warning(f"Pipeline: couldn't remove monitoring FIFO {monitor_fifo}: {e}")
            
            print("Pipeline stopped successfully")
            return {'success': True}
        except Exception as e:
            if pipeline_process:
                try:
                    pipeline_process.kill()
                except:
                    pass
                pipeline_process = None
            pipeline_running = False
            return {'success': False, 'error': str(e)}

def get_stats():
    """Get current statistics."""
    return {
        'packets_received': stats['packets_received'],
        'stations_heard': len(stats['stations_heard']),
        'direct_rf_senders': len(stats['direct_rf_senders']),
        'pipeline_running': pipeline_running
    }

# Routes

@app.route('/')
def index():
    return render_template('index.html')

def load_device_preset(device_name):
    """Load preset configuration from scripts/{device}.conf file"""
    preset_files = {
        'rtlsdr': 'scripts/rtlsdr.conf',
        'sdrplay': 'scripts/rsp1.conf',
    }
    
    config_file = preset_files.get(device_name)
    if not config_file or not os.path.exists(config_file):
        return None
    
    try:
        preset = {
            'device': device_name,
            'frequency': 144.8,
            'sample_rate': 1024000,
            'gain': 40.0,
            'ifgr': 40,
            'rfgr': 0,
            'agc': False,
            'filter_quality': '24k',
        }
        
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                
                key, value = parts
                
                if key == 'FREQUENCY':
                    preset['frequency'] = float(value)
                elif key == 'SAMPLE_RATE':
                    preset['sample_rate'] = int(value)
                elif key == 'AGC':
                    preset['agc'] = value.lower() in ('true', 'yes', '1', 'on')
                elif key == 'GAIN':
                    gain_parts = value.split(None, 1)
                    if len(gain_parts) == 2:
                        gain_name, gain_value = gain_parts
                        if gain_name.upper() == 'IFGR':
                            preset['ifgr'] = int(float(gain_value))
                        elif gain_name.upper() == 'RFGR':
                            preset['rfgr'] = int(float(gain_value))
                        elif gain_name.upper() == 'TUNER':
                            preset['ifgr'] = int(float(gain_value))
                elif key == 'BANDWIDTH':
                    # Map BANDWIDTH value directly to filter_quality for web UI
                    bw = value.strip().lower()
                    # Accept forms like 24k or 24000
                    if bw.endswith('k'):
                        preset['filter_quality'] = bw
                    else:
                        try:
                            hz = int(float(bw))
                            if hz >= 22000:
                                preset['filter_quality'] = '24k'
                            elif hz >= 11000:
                                preset['filter_quality'] = '12k'
                            elif hz >= 7000:
                                preset['filter_quality'] = '8k'
                            elif hz >= 5000:
                                preset['filter_quality'] = '6k'
                            else:
                                preset['filter_quality'] = '4k'
                        except Exception:
                            pass
        
        print(f"Loaded device preset for {device_name} from {config_file}: {preset}")
        return preset
    except Exception as e:
        print(f"Warning: Could not load preset from {config_file}: {e}")
        return None

# Initialize backend config from preset at startup so that /api/config
# reflects the device-specific defaults (frequency, sample rate, bandwidth).
_initial_preset = load_device_preset(config['device'])
if _initial_preset:
    try:
        config['frequency'] = _initial_preset.get('frequency', config['frequency'])
        config['sample_rate'] = _initial_preset.get('sample_rate', config['sample_rate'])
        config['ifgr'] = _initial_preset.get('ifgr', config['ifgr'])
        config['rfgr'] = _initial_preset.get('rfgr', config['rfgr'])
        config['agc'] = _initial_preset.get('agc', config['agc'])
        config['filter_quality'] = _initial_preset.get('filter_quality', config['filter_quality'])
        print(f"Initialized backend config from preset for {config['device']}: {config}")
    except Exception as e:
        print(f"Warning: Could not apply initial preset to config: {e}")

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def update_config():
    global config
    data = request.json
    
    print(f"Received config update: {data}")
    
    # Update config (supports multi-device parameters)
    if 'device' in data:
        config['device'] = data['device']
    if 'frequency' in data:
        config['frequency'] = float(data['frequency'])
    if 'sample_rate' in data:
        config['sample_rate'] = int(data['sample_rate'])
    if 'gain' in data:
        config['gain'] = float(data['gain'])
    if 'ifgr' in data:
        config['ifgr'] = int(data['ifgr'])
    if 'rfgr' in data:
        config['rfgr'] = int(data['rfgr'])
    if 'agc' in data:
        config['agc'] = bool(data['agc'])
    if 'filter_quality' in data:
        config['filter_quality'] = data['filter_quality']
    
    # Recalculate decimation
    config['decimation'] = max(1, int(config['sample_rate'] / 24000))
    
    print(f"Updated config: {config}")
    
    # Restart pipeline if running
    was_running = pipeline_running
    restart_status = None
    
    if was_running:
        print("Restarting pipeline with new config...")
        try:
            result = stop_pipeline()
            print(f"Stop result: {result}")
            
            if result['success']:
                print("Pipeline stopped, waiting before restart...")
                time.sleep(2)  # Wait longer for cleanup
                print("Starting pipeline after config change...")
                result = start_pipeline()
                print(f"Start result: {result}")
                
                if not result['success']:
                    restart_status = f"Failed to restart: {result.get('error', 'Unknown error')}"
                    print(restart_status)
                    return jsonify({'success': False, 'error': restart_status, 'config': config})
                else:
                    print("Pipeline restarted successfully")
            else:
                restart_status = f"Failed to stop pipeline: {result.get('error', 'Unknown error')}"
                print(restart_status)
                return jsonify({'success': False, 'error': restart_status, 'config': config})
        except Exception as e:
            error_msg = f"Exception during restart: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': error_msg, 'config': config})
    
    return jsonify({'success': True, 'config': config, 'restarted': was_running})

@app.route('/api/preset/<device>', methods=['GET'])
def load_preset(device):
    """Load preset configuration for a device from its .conf file"""
    preset = load_device_preset(device)
    if preset:
        return jsonify({'success': True, 'config': preset})
    else:
        return jsonify({'success': False, 'error': f'No preset found for {device}'}), 404

@app.route('/api/pipeline/start', methods=['POST'])
def api_start_pipeline():
    ensure_continuous_rssi_monitor_started()
    return jsonify(start_pipeline())

@app.route('/api/pipeline/stop', methods=['POST'])
def api_stop_pipeline():
    return jsonify(stop_pipeline())

@socketio.on('connect')
def _on_socket_connect():
    # If the UI is using Socket.IO, ensure the monitor is running so the
    # `continuous_rssi` stream is produced.
    ensure_continuous_rssi_monitor_started()

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    return jsonify(get_stats())

@app.route('/api/packets', methods=['GET'])
def api_get_packets():
    return jsonify(list(stats['last_packets']))

@app.route('/api/stations', methods=['GET'])
def api_get_stations():
    # Flatten into separate lines for direct and each digipeater
    station_rows = []
    for callsign, entry in stats['station_list'].items():
        # Direct row
        if entry['direct']['count'] > 0:
            station_rows.append({
                'callsign': callsign,
                'via': 'Direct',
                'count': entry['direct']['count'],
                'last_seen': entry['direct']['last_seen'],
                'rssi': entry['direct']['rssi'],
                'snr': entry['direct']['snr']
            })
        # Via rows
        for digi, info in entry['via'].items():
            station_rows.append({
                'callsign': callsign,
                'via': digi,
                'count': info['count'],
                'last_seen': info['last_seen'],
                'rssi': info['rssi'],
                'snr': info['snr']
            })
    # Sort by last_seen desc
    station_rows.sort(key=lambda r: r['last_seen'] or '', reverse=True)
    return jsonify(station_rows)

@app.route('/api/metrics', methods=['GET'])
def api_get_metrics():
    return jsonify({
        'rssi': list(stats['rssi_history']),
        'snr': list(stats['snr_history'])
    })

@app.route('/api/continuous_rssi', methods=['GET'])
def api_get_continuous_rssi():
    # Keep payload bounded by the deque maxlen (60 seconds @ 100ms).
    return jsonify(list(stats['continuous_rssi']))


@app.route('/api/versions', methods=['GET'])
def api_get_versions():
    """Report runtime versions for Socket.IO troubleshooting.

    This must reflect the *running server* environment (sys.executable), which
    may differ from an interactive shell on the same host.
    """

    def _pkg_version(dist_name: str):
        try:
            import importlib.metadata as md  # Python 3.8+
            return md.version(dist_name)
        except Exception:
            try:
                import pkg_resources as pr
                return pr.get_distribution(dist_name).version
            except Exception:
                return None

    return jsonify({
        'python': sys.version,
        'executable': sys.executable,
        'packages': {
            'flask': _pkg_version('flask'),
            'flask-socketio': _pkg_version('flask-socketio'),
            'python-socketio': _pkg_version('python-socketio'),
            'python-engineio': _pkg_version('python-engineio'),
        }
    })

if __name__ == '__main__':
    import logging
    # Disable Flask request logging completely
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    log.disabled = True
    
    # Disable socketio logging
    logging.getLogger('socketio').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.ERROR)
    
    # Start continuous RSSI monitoring thread
    ensure_continuous_rssi_monitor_started()
    
    print("Starting Direwolf Web Interface...")
    print("Open http://localhost:5000 in your browser")
    print("=" * 80)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False, allow_unsafe_werkzeug=True)
