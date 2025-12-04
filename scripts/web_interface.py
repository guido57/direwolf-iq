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
from datetime import datetime
from collections import defaultdict, deque

app = Flask(__name__)
app.config['SECRET_KEY'] = 'direwolf-sdr-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
pipeline_process = None
pipeline_running = False
pipeline_lock = threading.Lock()

# Configuration
# Now uses SoapySDR config files for multi-device support
config = {
    'device': 'rtlsdr',  # Device type: 'rtlsdr', 'sdrplay', 'airspy', 'hackrf'
    'frequency': 144.825,
    'sample_rate': 1024000,  # RTL-SDR: 1.024M, SDRplay: 192k
    'gain': 40.0,  # Device-specific (RTL-SDR TUNER: 0-50 dB, SDRplay IFGR: 20-59 dB)
    'agc': False,
    'filter_quality': 'high',  # 'standard' or 'high'
    'decimation': 64  # Calculated based on sample rate
}

# Statistics
stats = {
    'packets_received': 0,
    'stations_heard': set(),
    'direct_rf_senders': set(),
    'last_packets': deque(maxlen=50),
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
    """Parse direwolf output line for packet info."""
    # Example: [0.2] IR5AO>APMI04,IR5X,IZ5OQO-11,WIDE2*:... [RSSI=-28.1 dBFS (S9+19), SNR=32.0 dB]
    
    packet_match = re.search(r'\[[\d.]+\]\s+([^>]+)>([^:]+):(.*?)\s*\[RSSI=', line)
    metric_match = re.search(r'\[RSSI=([-\d.]+)\s+dBFS.*?SNR=([\d.]+)\s+dB\]', line)
    
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

def generate_soapysdr_config():
    """Generate a temporary SoapySDR config file from current settings."""
    config_path = '/tmp/web_interface_sdr.conf'
    
    # Determine sample rate decimation for output
    # After decimation, want ~24kHz output
    decimation = max(1, int(config['sample_rate'] / 24000))
    
    # Build config content
    config_content = f"""# Auto-generated config for web interface
DEVICE driver={config['device']}
FREQUENCY {config['frequency']}
SAMPLE_RATE {config['sample_rate']}
AGC {str(config['agc']).lower()}
"""
    
    # Add device-specific gain parameter
    if config['device'] == 'rtlsdr':
        config_content += f"GAIN TUNER {config['gain']}\n"
    elif config['device'] == 'sdrplay':
        # SDRplay uses IFGR (IF Gain Reduction) and RFGR (RF Gain Reduction)
        # For compatibility, map gain to IFGR
        ifgr = max(20, min(59, int(config['gain'])))
        config_content += f"GAIN IFGR {ifgr}\nGAIN RFGR 0\n"
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
    
    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        
        line = line.strip()
        # Print direwolf output to console
        print(line)
        
        # Parse audio level for continuous monitoring
        audio_level = parse_audio_level(line)
        if audio_level is not None:
            stats['last_audio_level'] = audio_level
        
        packet = parse_direwolf_line(line)
        
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
                    stats['station_list'][sender]['via'][digi] = {'count': 0, 'last_seen': None, 'rssi': None, 'snr': None}
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

# Signal power monitoring using tee to tap the pipeline
def continuous_rssi_monitor():
    """Background thread to compute RSSI every 100ms by tapping IQ stream."""
    global stats, pipeline_running
    
    import numpy as np
    import struct
    
    monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
    
    while True:
        if pipeline_running:
            try:
                # Open FIFO for reading IQ samples
                with open(monitor_fifo, 'rb') as fifo:
                    print(f"RSSI monitor: reading from {monitor_fifo}")
                    while pipeline_running:
                        # Read 100ms of IQ data: 24kHz * 0.1s = 2400 samples * 8 bytes (CF32)
                        chunk_size = 2400 * 8
                        data = fifo.read(chunk_size)
                        
                        if len(data) < chunk_size:
                            break
                        
                        # Parse CF32 (float32 I, float32 Q interleaved)
                        num_floats = len(data) // 4
                        samples = struct.unpack(f'<{num_floats}f', data)
                        
                        # Convert to complex
                        iq = np.array(samples, dtype=np.float32)
                        iq_complex = iq[0::2] + 1j * iq[1::2]
                        
                        # Compute power in dBFS
                        power = np.mean(np.abs(iq_complex)**2)
                        if power > 0:
                            rssi_dbfs = 10 * np.log10(power)
                        else:
                            rssi_dbfs = -100
                        
                        rssi_dbfs = max(-100, min(0, rssi_dbfs))
                        
                        timestamp = datetime.now().isoformat()
                        stats['continuous_rssi'].append({
                            'time': timestamp,
                            'value': rssi_dbfs
                        })
                        
                        # Emit to clients
                        socketio.emit('continuous_rssi', {
                            'time': timestamp,
                            'value': rssi_dbfs
                        })
                        
            except FileNotFoundError:
                print(f"RSSI monitor: waiting for FIFO {monitor_fifo}")
                time.sleep(1)
            except Exception as e:
                print(f"RSSI monitor error: {e}")
                time.sleep(1)
        else:
            time.sleep(0.5)

def start_pipeline():
    """Start the SDR→direwolf pipeline with IQ tapping for continuous RSSI."""
    global pipeline_process, pipeline_running
    
    with pipeline_lock:
        if pipeline_running:
            return {'success': False, 'error': 'Pipeline already running'}
        
        try:
            # Create named pipe for monitoring
            monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
            try:
                if os.path.exists(monitor_fifo):
                    os.remove(monitor_fifo)
                os.mkfifo(monitor_fifo)
                print(f"Created monitoring FIFO: {monitor_fifo}")
            except Exception as e:
                print(f"Warning: couldn't create FIFO: {e}")
            
            # Generate SoapySDR config file
            sdr_config = generate_soapysdr_config()
            print(f"Generated SoapySDR config: {sdr_config}")
            
            # Calculate decimation and output rate
            decimation = max(1, int(config['sample_rate'] / 24000))
            output_rate = config['sample_rate'] // decimation
            
            # Build command with generic SoapySDR interface
            filter_arg = f"{decimation} 0.005 HAMMING" if config['filter_quality'] == 'high' else str(decimation)
            
            # Use soapysdr_to_direwolf.py for multi-device support
            sdr_cmd = f"python3 scripts/soapysdr_to_direwolf.py --config {sdr_config}"
            
            # Add tee after decimation (at direwolf input) for accurate RSSI measurement
            full_cmd = (
                f"{sdr_cmd} 2>/dev/null | "
                f"csdr fir_decimate_cc {filter_arg} 2>/dev/null | "
                f"tee {monitor_fifo} | "
                f"./build/src/direwolf -M -t 0 -r {output_rate} -n 1 iq:{output_rate} 2>&1"
            )
            
            print(f"Starting pipeline with command: {full_cmd}")
            print(f"Config: device={config['device']}, freq={config['frequency']}, sample_rate={config['sample_rate']}, decimation={decimation}")
            
            cmd = ['bash', '-c', full_cmd]
            
            pipeline_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
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
                pipeline_process.terminate()
                pipeline_process.wait(timeout=5)
            pipeline_running = False
            
            # Clean up monitoring FIFO
            monitor_fifo = '/tmp/direwolf_iq_monitor.fifo'
            import os
            try:
                if os.path.exists(monitor_fifo):
                    os.remove(monitor_fifo)
                    print(f"Removed monitoring FIFO: {monitor_fifo}")
            except Exception as e:
                print(f"Warning: couldn't remove FIFO: {e}")
            
            return {'success': True}
        except Exception as e:
            if pipeline_process:
                pipeline_process.kill()
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
    if 'agc' in data:
        config['agc'] = bool(data['agc'])
    if 'filter_quality' in data:
        config['filter_quality'] = data['filter_quality']
    
    # Recalculate decimation
    config['decimation'] = max(1, int(config['sample_rate'] / 24000))
    
    print(f"Updated config: {config}")
    
    # Restart pipeline if running
    if pipeline_running:
        stop_pipeline()
        time.sleep(1)
        start_pipeline()
    
    return jsonify({'success': True, 'config': config})

@app.route('/api/pipeline/start', methods=['POST'])
def api_start_pipeline():
    return jsonify(start_pipeline())

@app.route('/api/pipeline/stop', methods=['POST'])
def api_stop_pipeline():
    return jsonify(stop_pipeline())

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

if __name__ == '__main__':
    import logging
    # Disable Flask request logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    # Start continuous RSSI monitoring thread
    monitor_thread = threading.Thread(target=continuous_rssi_monitor, daemon=True)
    monitor_thread.start()
    
    print("Starting Direwolf Web Interface...")
    print("Open http://localhost:5000 in your browser")
    print("=" * 80)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False)
