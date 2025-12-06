# SoapySDR to Direwolf - Unified Script

`soapysdr_to_direwolf.py` is a unified script that provides three modes:
1. **Direct streaming**: Pipe IQ samples to other tools via stdout
2. **Command-line launcher**: Run complete pipeline (SDR → decimation → direwolf)
3. **Web interface**: Full monitoring dashboard with real-time statistics

All three modes use the same configuration files and SoapySDR infrastructure.

## Features

- **Command-line mode**: Simple pipeline execution with any SDR config
- **Web interface mode**: Real-time monitoring with RSSI graphs and station tracking
- **Persistent statistics**: Web interface accumulates stats even when browser is closed
- **Unified configuration**: Uses the same `.conf` files for both modes
- **Auto-detection**: Finds direwolf binary and config files automatically

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

### Mode 4: Web-Only Mode (Manual Start)

Start web interface without auto-starting pipeline:
```bash
python3 scripts/soapysdr_to_direwolf.py --launcher --web --no-autostart
```

Use the web UI controls to manually configure and start the pipeline.

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

```
soapysdr_to_direwolf.py (192 kHz)
  ↓
csdr fir_decimate_cc (decimation)
  ↓
tee /tmp/direwolf_iq_monitor.fifo  (only with --web)
  ↓
direwolf (24 kHz IQ input)
```

When `--web` is used, the FIFO allows the web interface to monitor continuous RSSI in parallel with direwolf's packet decoding.

## Stopping

Press `Ctrl+C` to gracefully stop the pipeline and clean up resources.
