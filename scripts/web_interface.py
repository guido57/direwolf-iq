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
config = {
    'frequency': 144.8,
    'ifgr': 23,
    'rfgr': 0,
    'agc': False,
    'filter_quality': 'high'  # 'standard' or 'high'
}

# Statistics
stats = {
    'packets_received': 0,
    'stations_heard': set(),
    'direct_rf_senders': set(),
    'last_packets': deque(maxlen=50),
    'rssi_history': deque(maxlen=100),
    'snr_history': deque(maxlen=100),
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

def pipeline_reader(process):
    """Read direwolf output and update statistics."""
    global stats
    
    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        
        line = line.strip()
        # Print direwolf output to console
        print(line)
        
        packet = parse_direwolf_line(line)
        
        if packet:
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

def start_pipeline():
    """Start the SDR→direwolf pipeline."""
    global pipeline_process, pipeline_running
    
    with pipeline_lock:
        if pipeline_running:
            return {'success': False, 'error': 'Pipeline already running'}
        
        try:
            # Build command
            filter_arg = '4 0.005 HAMMING' if config['filter_quality'] == 'high' else '4'
            
            # Build sdrplay command parts
            sdr_cmd = (
                f"python3 scripts/sdrplay_to_direwolf.py "
                f"--freq {config['frequency']} "
                f"--ifgr {config['ifgr']} "
                f"--rfgr {config['rfgr']}"
            )
            
            # Add --agc flag if enabled
            if config['agc']:
                sdr_cmd += " --agc"
            
            full_cmd = (
                f"{sdr_cmd} 2>/dev/null | "
                f"csdr fir_decimate_cc {filter_arg} 2>/dev/null | "
                f"./build/src/direwolf -M -t 0 -r 48000 -n 1 iq:48000 2>&1"
            )
            
            print(f"Starting pipeline with command: {full_cmd}")
            
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
            return {'success': True}
        except Exception as e:
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
    
    # Update config
    if 'frequency' in data:
        config['frequency'] = float(data['frequency'])
    if 'ifgr' in data:
        config['ifgr'] = int(data['ifgr'])
    if 'rfgr' in data:
        config['rfgr'] = int(data['rfgr'])
    if 'agc' in data:
        config['agc'] = bool(data['agc'])
    if 'filter_quality' in data:
        config['filter_quality'] = data['filter_quality']
    
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
    
    print("Starting Direwolf Web Interface...")
    print("Open http://localhost:5000 in your browser")
    print("=" * 80)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=False)
