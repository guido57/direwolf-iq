#!/usr/bin/env python3
"""
Monitor direwolf output and send APRS-IS message when RF packet is received.
Sends alert to IW5ALZ-12 via APRS-IS whenever any RF packet is decoded.
"""

import sys
import socket
import time
import re
from datetime import datetime

# Configuration
APRS_SERVER = "rotate.aprs2.net"  # or "euro.aprs2.net"
APRS_PORT = 14580
YOUR_CALLSIGN = "IW5ALZ-12"  # Your receiving callsign
YOUR_PASSCODE = "XXXXX"  # Calculate at https://apps.magicbug.co.uk/passcode/
ALERT_TO = "IW5ALZ-12"  # Who to send the message to (you)

# State tracking
last_alert_time = 0
ALERT_COOLDOWN = 300  # Send alert at most once every 5 minutes

def calculate_aprs_passcode(callsign):
    """
    Calculate APRS passcode for a callsign.
    Note: This is a basic implementation. For production use,
    get your passcode from https://apps.magicbug.co.uk/passcode/
    """
    callsign = callsign.split('-')[0].upper()  # Remove SSID
    hash_value = 0x73e2
    for char in callsign:
        hash_value ^= ord(char) << 8
        hash_value ^= ord(char)
    return hash_value & 0x7fff

def connect_aprs_is():
    """Connect to APRS-IS server"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((APRS_SERVER, APRS_PORT))
        
        # Receive server greeting
        greeting = sock.recv(1024).decode('utf-8', errors='ignore')
        print(f"APRS-IS: {greeting.strip()}", file=sys.stderr)
        
        # Send login
        login = f"user {YOUR_CALLSIGN} pass {YOUR_PASSCODE} vers rf_alert 1.0\r\n"
        sock.send(login.encode('utf-8'))
        
        # Receive login response
        response = sock.recv(1024).decode('utf-8', errors='ignore')
        print(f"APRS-IS: {response.strip()}", file=sys.stderr)
        
        if "verified" in response.lower():
            print("✓ Connected to APRS-IS successfully", file=sys.stderr)
            return sock
        else:
            print("✗ APRS-IS login failed - check callsign and passcode", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"✗ Failed to connect to APRS-IS: {e}", file=sys.stderr)
        return None

def send_aprs_message(sock, from_call, to_call, message):
    """Send an APRS message"""
    try:
        # APRS message format: FROM>APRS,TCPIP*::TO_CALL__:message
        # To callsign must be exactly 9 characters (padded with spaces)
        to_padded = to_call.ljust(9)
        msg_id = int(time.time()) % 1000  # Simple message ID
        
        packet = f"{from_call}>APRS,TCPIP*::{to_padded}:{message}{{{msg_id}\r\n"
        sock.send(packet.encode('utf-8'))
        print(f"→ Sent APRS message to {to_call}: {message}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"✗ Failed to send APRS message: {e}", file=sys.stderr)
        return False

def parse_direwolf_line(line):
    """
    Parse direwolf output line to detect RF packets.
    Returns (callsign, rssi, snr) if RF packet detected, else None
    """
    # Look for lines with RSSI/SNR metrics (indicates RF reception)
    # Example: [0.2] IR5AO>APMI04,IR5X,... [RSSI=-28.1 dBFS (S9+19), SNR=32.0 dB]
    
    match = re.search(r'\[[\d.]+\]\s+(\S+)>.*\[RSSI=([-\d.]+)\s+dBFS.*SNR=([\d.]+)\s+dB\]', line)
    if match:
        callsign = match.group(1)
        rssi = match.group(2)
        snr = match.group(3)
        return (callsign, rssi, snr)
    
    # Also detect RF packets without metrics
    # Example: IR5AO>APMI04,IR5X,IZ5OQO-11,WIDE2*:...
    match = re.search(r'\[[\d.]+\]\s+(\S+)>.*audio level\s*=\s*(\d+)', line)
    if match:
        callsign = match.group(1)
        return (callsign, None, None)
    
    return None

def main():
    global last_alert_time
    
    print("RF Alert Monitor for Direwolf", file=sys.stderr)
    print(f"Will send APRS-IS alerts to {ALERT_TO}", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Check if passcode is set
    if YOUR_PASSCODE == "XXXXX":
        print("", file=sys.stderr)
        print("⚠ WARNING: APRS passcode not configured!", file=sys.stderr)
        print("Edit this script and set YOUR_PASSCODE", file=sys.stderr)
        print(f"Calculate it at: https://apps.magicbug.co.uk/passcode/", file=sys.stderr)
        print(f"Or use: {calculate_aprs_passcode(YOUR_CALLSIGN)}", file=sys.stderr)
        print("", file=sys.stderr)
        return 1
    
    # Connect to APRS-IS
    aprs_sock = connect_aprs_is()
    if not aprs_sock:
        print("Cannot continue without APRS-IS connection", file=sys.stderr)
        return 1
    
    print("", file=sys.stderr)
    print("Monitoring direwolf output for RF packets...", file=sys.stderr)
    print("(Press Ctrl+C to stop)", file=sys.stderr)
    print("", file=sys.stderr)
    
    try:
        # Read direwolf output from stdin
        for line in sys.stdin:
            # Print the line (pass through)
            print(line, end='')
            sys.stdout.flush()
            
            # Check for RF packet
            packet_info = parse_direwolf_line(line)
            if packet_info:
                callsign = packet_info[0]
                rssi = packet_info[1]
                snr = packet_info[2]
                
                # Check cooldown
                now = time.time()
                if now - last_alert_time < ALERT_COOLDOWN:
                    time_left = int(ALERT_COOLDOWN - (now - last_alert_time))
                    print(f"  (Alert cooldown: {time_left}s remaining)", file=sys.stderr)
                    continue
                
                # Send alert
                timestamp = datetime.now().strftime("%H:%M:%S")
                if rssi and snr:
                    message = f"RF RX {timestamp}: {callsign} RSSI={rssi}dB SNR={snr}dB"
                else:
                    message = f"RF RX {timestamp}: {callsign}"
                
                if send_aprs_message(aprs_sock, YOUR_CALLSIGN, ALERT_TO, message):
                    last_alert_time = now
                    print(f"✓ Alert sent (next alert in {ALERT_COOLDOWN}s)", file=sys.stderr)
                    
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    except BrokenPipeError:
        print("\nDirewolf stopped.", file=sys.stderr)
    finally:
        if aprs_sock:
            aprs_sock.close()
            print("Disconnected from APRS-IS", file=sys.stderr)

if __name__ == '__main__':
    sys.exit(main())
