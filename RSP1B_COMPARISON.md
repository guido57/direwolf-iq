# RSP1B Noise Floor Comparison: Ubuntu vs Raspberry Pi

## Summary Results

### Noise Floor Measurements

| Sample Rate | Ubuntu | Pi | Difference |
|---|---|---|---|
| **250 kHz** | -33.11 dBFS | -33.75 dBFS | **+0.64 dB (Pi better)** |
| **1024 kHz** | -33.22 dBFS | -33.06 dBFS | **-0.16 dB (Ubuntu slightly better)** |
| **2048 kHz** | -24.74 dBFS | -24.94 dBFS | **+0.20 dB (Pi slightly better)** |

### Key Observation: **RSP1B Shows NO Significant Platform Difference!**

The noise floor is nearly identical on both Ubuntu and Raspberry Pi Zero 2 W, with **maximum deviation of only ±0.64 dB** across all sample rates.

---

## Comparison with RTL-SDR Results

### RTL-SDR Platform Difference (from earlier tests)
- 250 kHz: Ubuntu -40 dBFS vs Pi -25.5 dBFS = **14.5 dB difference** ❌
- USB controller limited on Pi

### RSP1B Platform Difference
- 250 kHz: Ubuntu -33.11 dBFS vs Pi -33.75 dBFS = **0.64 dB difference** ✅
- **No significant platform difference!**

---

## Sample Rate Degradation Comparison

### Ubuntu
| Rate | RSP1B Noise Floor | Degradation from 250 kHz |
|---|---|---|
| 250 kHz | -33.11 dBFS | Baseline |
| 1024 kHz | -33.22 dBFS | -0.11 dB (essentially flat) |
| 2048 kHz | -24.74 dBFS | +8.37 dB degradation |

### Raspberry Pi
| Rate | RSP1B Noise Floor | Degradation from 250 kHz |
|---|---|---|
| 250 kHz | -33.75 dBFS | Baseline |
| 1024 kHz | -33.06 dBFS | +0.69 dB (essentially flat) |
| 2048 kHz | -24.94 dBFS | +8.81 dB degradation |

**Both platforms show same pattern**: 250-1024 kHz is stable, then 8 dB degradation at 2048 kHz.

---

## Auto-Gain Behavior

The RSP1B adjusts gain automatically at different sample rates:

| Sample Rate | Ubuntu Gain | Pi Gain |
|---|---|---|
| 250 kHz | 30.0 dB | 30.0 dB |
| 1024 kHz | 16.0 dB | 15.0 dB |
| 2048 kHz | 14.0 dB | 14.0 dB |

The gain reduction at higher sample rates is **identical on both platforms**, suggesting the RSP1B has proper firmware control over gain scaling.

---

## Critical Finding: RSP1B vs RTL-SDR

### RTL-SDR Comparison
- **Ubuntu**: -40 dBFS @ 250 kHz
- **Pi**: -25.5 dBFS @ 250 kHz
- **Difference**: 14.5 dB (USB controller issue on Pi)

### RSP1B Comparison
- **Ubuntu**: -33.11 dBFS @ 250 kHz
- **Pi**: -33.75 dBFS @ 250 kHz
- **Difference**: 0.64 dB (essentially no difference!)

**The RSP1B is far superior for Raspberry Pi deployment** because it uses a proper USB interface protocol that doesn't suffer from the Pi's USB controller limitations.

---

## Recommendation

For Raspberry Pi Zero 2 W deployment:
- **RSP1B is recommended over RTL-SDR** (much cleaner noise floor: -33.75 vs -25.5 dBFS)
- **No performance penalty on Pi vs Ubuntu** (only 0.64 dB difference at 250 kHz)
- **Better dynamic range** for weak signal reception
- **Supports higher sample rates** without significant degradation (stays above -33 dBFS up to 1024 kHz)

---

## Notes on 2048 kHz Measurements

Both platforms show **identical degradation at 2048 kHz** (-24.74 to -24.94 dBFS), suggesting this is a:
- Tuner characteristic (not USB controller related)
- Possible firmware quirk on RSP1B at very high sample rates
- Not a platform limitation (both Ubuntu and Pi affected equally)

The high standard deviation (7.38-7.55 dB) at 2048 kHz suggests the automatic gain control is making large adjustments, which is why noise floor stability degrades significantly at this rate.
