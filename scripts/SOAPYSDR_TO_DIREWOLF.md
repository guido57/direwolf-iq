# SoapySDR to Direwolf - Unified Script

`soapysdr_to_direwolf.py` is a unified script that ties SoapySDR-based devices into Direwolf.

It provides four closely related modes:
1. **Direct streaming**: Pipe IQ samples to other tools via stdout
2. **Command-line launcher**: Run complete pipeline (SDR → decimation → Direwolf)
3. **Launcher + web interface**: Full monitoring dashboard with real-time statistics
4. **Web-only**: Start the web UI without auto-starting the RF pipeline

All modes share the same SoapySDR configuration files and logging.

## Features

- **Command-line mode**: Simple pipeline execution with any SDR config
- **Web interface mode**: Real-time monitoring with RSSI graphs, station tracking, and channel bandwidth control
- **Persistent statistics**: Web interface accumulates stats even when browser is closed
- **Unified configuration**: Uses the same `.conf` files for both modes
- **Auto-detection**: Finds direwolf binary and config files automatically
 - **Watchdog & logging**: Automatically restarts stalled SDR streams and logs events to `scripts/direwolf_iq.log`

## Usage Modes

### Mode 1: Direct Streaming (default, no launcher)

Stream IQ samples to stdout for custom processing:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rtlsdr.conf | csdr fir_decimate_cc 8 | direwolf -M -t 0 -r 24000 -n 1 iq:24000
```

### Mode 2: Command-Line Launcher

Run a complete pipeline (SDR → decimation → tee → direwolf):
```bash
python3 scripts/soapysdr_to_direwolf.py --config rtlsdr.conf --launcher
python3 scripts/soapysdr_to_direwolf.py --config rsp1.conf --launcher --direwolf-config ~/direwolf.conf
```

### Mode 3: Web Interface Mode

Launch with real-time web monitoring:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rsp1.conf --launcher --web
```

Then open http://localhost:5000 in your browser.

**Features when using `--launcher --web`:**
- Real-time continuous RSSI monitor (100ms samples)
- Decoded packet display with peak RSSI/SNR
- Station list with direct vs. digipeated tracking
- Live charts with collision-avoiding labels
- Statistics persist even when browser is closed
 - "Channel Bandwidth" control (24k/12k/8k/6k/4k) backed by a Python FIR (`iq_lowpass.py`)

### Mode 4: Web-Only Mode (Manual Start)

Start web interface without auto-starting pipeline:
```bash
python3 scripts/soapysdr_to_direwolf.py --launcher --web --no-autostart
```

Use the web UI controls to manually configure and start the pipeline.

In this mode the UI can generate a fresh SoapySDR config (including center frequency, sample rate, AGC and bandwidth preset) and then start the full pipeline on demand.

## Configuration Files

Example configs live in `scripts/`:

- `rtlsdr.conf` – RTL-SDR (RTL2832U)
- `rsp1.conf` – SDRplay RSP1

Common keys understood by `soapysdr_to_direwolf.py`:

- `DEVICE` – SoapySDR device string, e.g. `driver=rtlsdr` or `driver=sdrplay`
- `FREQUENCY` – Center frequency in MHz (e.g. `144.800`)
- `SAMPLE_RATE` – Complex sample rate in Hz from the SDR (e.g. `1024000` or `2048000`)
- `BANDWIDTH` – Default channel bandwidth mode for the web UI: `24k,12k,8k,6k,4k`
- `AGC` – `true/false` to enable/disable device AGC
- `GAIN ...` – Device-specific gain lines, e.g. `GAIN TUNER 35.0` for RTL-SDR or `GAIN IFGR 35` / `GAIN RFGR 0` for SDRplay
- `SETTING ...` – Additional SoapySDR driver settings, e.g. `SETTING offset_tune false`

## Command-Line Options

```
--config, -c          SDR config file (default: soapysdr.conf)
--device              Device type: sdrplay, rtlsdr, airspy, hackrf, or auto
--freq                Frequency in MHz (default: from config or 144.8)
--gain                Gain in dB (device-specific)
--agc                 Enable automatic gain control
--list-devices        List all available SoapySDR devices and exit

--launcher            Enable unified launcher mode (combines SDR + decimation + direwolf)
--direwolf-config, -d Direwolf config file (for launcher mode)
--web, -w             Enable web interface for monitoring (launcher mode)
--no-autostart        Start web interface without auto-starting pipeline
--list-configs        List available config files and exit

Device-specific (direct streaming mode only):
  --ifgr              SDRplay IF Gain Reduction (20-59)
  --rfgr              SDRplay RF Gain Reduction (0-3)
  --lna               Airspy LNA gain (0-15)
  --mixer             Airspy Mixer gain (0-15)
  --vga               Airspy VGA gain (0-15)
```

## Examples

Direct streaming to custom pipeline:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rtlsdr --freq 144.8 | csdr fir_decimate_cc 8 | direwolf -M
```

Command-line launcher with RTL-SDR:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rtlsdr --launcher
```

Launcher with custom direwolf config:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rsp1 --launcher --direwolf-config ~/my-direwolf.conf
```

Web monitoring:
```bash
python3 scripts/soapysdr_to_direwolf.py --config rsp1 --launcher --web
```

Manual web mode (no pipeline):
```bash
python3 scripts/soapysdr_to_direwolf.py --launcher --web --no-autostart
```

List available configs:
```bash
python3 scripts/soapysdr_to_direwolf.py --list-configs
```

## Pipeline Architecture

### Launcher (no web)

```
SoapySDR device (sample_rate from *.conf)
  ↓
soapysdr_to_direwolf.py  (direct IQ stream, watchdog, logging)
  ↓
csdr fir_decimate_cc <decimation> 0.005 HAMMING
  ↓
Direwolf iq:<output_rate>  (≈ 24 kHz complex IQ)
```

`decimation` is chosen so that `output_rate = SAMPLE_RATE // decimation` is close to 24000 Hz.

### Launcher + Web Interface

```
SoapySDR device (sample_rate from *.conf)
  ↓
soapysdr_to_direwolf.py  (direct IQ stream, watchdog, logging)
  ↓
csdr fir_decimate_cc <decimation> 0.005 HAMMING
  ↓
iq_lowpass.py --rate <output_rate> --mode <24k|12k|8k|6k|4k>
  ↓
tee /tmp/direwolf_iq_monitor.fifo
  ↓
Direwolf iq:<output_rate>
```

When `--web` is used, the FIFO lets the web interface read IQ samples for the continuous RSSI chart while Direwolf continues decoding packets.

The `iq_lowpass.py` stage implements an additional complex FIR low-pass, controlled by the "Channel Bandwidth" selector in the web UI.

High-level view of Mode 3 (launcher + web):

```
  +---------+      +--------------------------------------------+      +-------------------------------------------+
  | Antenna | ---> | SDR (SoapySDR dev, e.g. RTL-SDR 250k–2.048M) | ---> | Decimator (csdr fir_dec..., to 24 kS/s) |
  +---------+      +--------------------------------------------+      +-------------------------------------------+
                                                             |
                                                             v
                                  +-------------------------------------------+
                                  | Low-pass FIR (iq_lowpass.py, 24k..4k)    |
                                  +-------------------------------------------+
                                                             |
                                                             v
                     +------------------------------------------------+
                     | Direwolf (IQ input @ 24 kS/s, demod + decode) |
                     +------------------------------------------------+
                               |                               |
                               v                               v
      +---------------------------------------+   +-----------------------------+
      | Web Interface (Flask/Socket.IO UI)   |   | Console (Direwolf stdout)   |
      +---------------------------------------+   +-----------------------------+
```

## Watchdog and Logging

- A built-in watchdog in `run_direct_streaming()` monitors SoapySDR reads:
  - If no valid samples are seen for ~10 seconds, the SDR stream is torn down and re-initialized.
  - This automatically recovers from rare USB/driver stalls without stopping Direwolf.
- All high-level events (device detection, configuration, watchdog restarts, etc.) are logged to `scripts/direwolf_iq.log`.
- The web backend (`web_interface.py`) writes Direwolf output and RSSI monitor errors to the same log, so you have a single place to inspect problems.

## Stopping

Press `Ctrl+C` to gracefully stop the pipeline and clean up resources.
