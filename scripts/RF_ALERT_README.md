# RF Alert Script

Monitors direwolf output and sends APRS-IS messages to IW5ALZ-12 whenever RF packets are received.

## Setup

1. **Get your APRS-IS passcode:**
   - Visit: https://apps.magicbug.co.uk/passcode/
   - Enter your callsign: `IW5ALZ-12`
   - Copy the passcode

2. **Edit the script:**
   ```bash
   nano scripts/rf_alert.py
   ```
   
   Change this line:
   ```python
   YOUR_PASSCODE = "XXXXX"  # Replace with your actual passcode
   ```

3. **Verify configuration:**
   ```python
   YOUR_CALLSIGN = "IW5ALZ-12"  # Your callsign
   ALERT_TO = "IW5ALZ-12"       # Who receives alerts (you)
   ALERT_COOLDOWN = 300         # Minimum seconds between alerts (5 minutes)
   ```

## Usage

**Basic usage** (pipe direwolf output through the script):
```bash
cd /home/guido/Documents/PlatformIO/Projects/direwolf-iq

# With live SDR:
python3 scripts/sdrplay_to_direwolf.py | \
  csdr fir_decimate_cc 4 | \
  ./build/src/direwolf -M -t 0 -r 48000 -n 1 iq:48000 2>&1 | \
  python3 scripts/rf_alert.py
```

**With audio monitoring:**
```bash
python3 scripts/sdrplay_to_direwolf.py | \
  tee >(csdr fir_decimate_cc 4 | csdr fmdemod_quadri_cf | csdr limit_ff | csdr convert_f_s16 | aplay -r 48000 -f S16_LE -c 1) | \
  csdr fir_decimate_cc 4 | \
  ./build/src/direwolf -M -t 0 -r 48000 -n 1 iq:48000 2>&1 | \
  python3 scripts/rf_alert.py
```

## What it does

- Monitors direwolf output for RF packets (those with RSSI/SNR metrics)
- When a packet is received, sends an APRS message to IW5ALZ-12 via APRS-IS
- Message format: `RF RX HH:MM:SS: CALLSIGN RSSI=-XX.XdB SNR=XX.XdB`
- Cooldown period: 5 minutes between alerts (configurable)

## Example output

```
APRS-IS: # aprsc 2.1.14-g28c5a6a 29 Dec 2024 14:52:03 GMT EURO T2SPAIN
APRS-IS: # logresp IW5ALZ-12 verified, server T2SPAIN
✓ Connected to APRS-IS successfully

Monitoring direwolf output for RF packets...

[0.2] IR5AO>APMI04,IR5X,IZ5OQO-11,WIDE2*:... [RSSI=-28.1 dBFS (S9+19), SNR=32.0 dB]
→ Sent APRS message to IW5ALZ-12: RF RX 14:52:15: IR5AO RSSI=-28.1dB SNR=32.0dB
✓ Alert sent (next alert in 300s)
```

## Troubleshooting

**"APRS-IS login failed":**
- Check your callsign spelling
- Verify your passcode is correct
- Ensure internet connection is working

**No alerts being sent:**
- Check that direwolf is actually decoding RF packets
- Verify the `-M` flag is used (enables metrics)
- Check cooldown period hasn't blocked alerts

**Message not received:**
- Check APRS-IS status on aprs.fi or similar
- Verify your callsign can send messages (validated SSID)
- Check APRS client on receiving end

## Customization

Edit the script to change:
- `APRS_SERVER`: Change server (default: `rotate.aprs2.net`)
- `ALERT_COOLDOWN`: Change time between alerts (seconds)
- `ALERT_TO`: Send to different callsign
- Message format in `send_aprs_message()` function
