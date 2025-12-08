# SDR Scripts

This directory contains Python scripts for streaming IQ data from SDR devices to direwolf.

## Available Scripts

### soapysdr_to_direwolf.py (Recommended)

**Generic SoapySDR wrapper supporting multiple devices:**
- SDRplay RSP1/RSP2/RSPduo
- RTL-SDR (RTL2832U)
- Airspy R2/Mini
- HackRF One
- Any SoapySDR-supported device

**Features:**
- Auto-detection of devices
- Configuration file support
- Device-specific gain controls
- Better error handling

**Documentation:** See [SOAPYSDR_TO_DIREWOLF.md](SOAPYSDR_TO_DIREWOLF.md)

**Quick start:**
```bash
# Auto-detect device
python3 scripts/soapysdr_to_direwolf.py --freq 144.8

# Specific device with gains
python3 scripts/soapysdr_to_direwolf.py --device sdrplay --freq 144.8 --ifgr 23
python3 scripts/soapysdr_to_direwolf.py --device rtlsdr --freq 144.8 --gain 40
python3 scripts/soapysdr_to_direwolf.py --device airspy --freq 144.8 --lna 10 --mixer 10
```

### sdrplay_to_direwolf.py (Legacy)

**SDRplay-specific script (original implementation):**
- Supports RSP1, RSP2, RSPduo
- Simpler, focused on SDRplay devices only
- Maintained for backward compatibility

**Usage:**
```bash
python3 scripts/sdrplay_to_direwolf.py --freq 144.8 --ifgr 23 --rfgr 0
```

**Note:** For new projects, use `soapysdr_to_direwolf.py` instead.

## Migration from sdrplay_to_direwolf.py

If you're using `sdrplay_to_direwolf.py`, migration is simple:

**Old command:**
```bash
python3 scripts/sdrplay_to_direwolf.py --freq 144.8 --ifgr 23 --rfgr 0
```

**New command:**
```bash
python3 scripts/soapysdr_to_direwolf.py --device sdrplay --freq 144.8 --ifgr 23 --rfgr 0
```

Or use a config file:
```bash
# Edit soapysdr_config.yaml with your settings
python3 scripts/soapysdr_to_direwolf.py --config soapysdr_config.yaml
```

## Dependencies

**Required:**
```bash
sudo apt install python3-soapysdr python3-numpy csdr
```

**Optional (for config file support):**
```bash
sudo apt install python3-yaml
```

**Device-specific drivers:**
- SDRplay: Install API from https://www.sdrplay.com/
- RTL-SDR: `sudo apt install rtl-sdr`
- Airspy: `sudo apt install airspy`
- HackRF: `sudo apt install hackrf`

## Testing

### With Real SDR

```bash
python3 scripts/soapysdr_to_direwolf.py --list-devices
python3 scripts/soapysdr_to_direwolf.py --freq 144.8 | \
  csdr fir_decimate_cc 8 | \
  direwolf -M -t 0 -r 24000 -n 1 iq:24000
```

### With Test File

```bash
cd test/iq
cat iq48k_cfloat.raw | \
  ../../build/src/direwolf -M -t 0 -r 48000 -n 1 iq:48000 2>&1 | \
  grep "^\[0"
```

## See Also

- [SOAPYSDR_TO_DIREWOLF.md](SOAPYSDR_TO_DIREWOLF.md) - Unified script with launcher and web interface
- [SoapySDR Documentation](https://github.com/pothosware/SoapySDR/wiki) - Official SoapySDR API and device guides
- [../IQ_INPUT.md](../IQ_INPUT.md) - Direwolf IQ input documentation
- [../README.md](../README.md) - Main direwolf documentation
