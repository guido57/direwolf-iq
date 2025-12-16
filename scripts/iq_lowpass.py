#!/usr/bin/env python3
"""Simple streaming complex IQ low-pass FIR filter.

Reads CF32 IQ (float32 interleaved I,Q) from stdin and writes filtered
CF32 IQ to stdout at the same sample rate. Intended to sit between
`csdr fir_decimate_cc` and Direwolf.

Usage (example, after decimation to ~24 kHz):

  python3 iq_lowpass.py --rate 24000 --mode 6k

Modes (interpreted as approximate RF channel widths):
  24k : pass-through (no extra filtering)
  12k : ~6 kHz audio cutoff
  8k  : ~4 kHz audio cutoff
  6k  : ~3 kHz audio cutoff
  4k  : ~2 kHz audio cutoff

The exact cutoff is clamped to stay below Nyquist if needed.
"""

import sys
import argparse
import numpy as np


def design_lowpass(sample_rate: float, cutoff_hz: float, num_taps: int = 129) -> np.ndarray:
    """Design a real-valued low-pass FIR using a Hamming window.

    sample_rate: input sample rate in Hz
    cutoff_hz: desired cutoff frequency in Hz (0 < f_c < sample_rate/2)
    num_taps: number of taps (odd preferred)
    """\

    nyq = sample_rate / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyq:
        raise ValueError("cutoff_hz must be between 0 and Nyquist")

    # Normalized cutoff for np.sinc (relative to sample_rate)
    fc_norm = cutoff_hz / sample_rate

    # Time index centered at (num_taps-1)/2
    n = np.arange(num_taps, dtype=np.float64)
    m = (num_taps - 1) / 2.0

    # Ideal low-pass (sinc) and Hamming window
    h = np.sinc(2.0 * fc_norm * (n - m))
    h *= np.hamming(num_taps)

    # Normalize to unity gain at DC
    h /= np.sum(h)

    return h.astype(np.float32)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Streaming IQ low-pass FIR filter")
    p.add_argument("--rate", type=float, required=True,
                   help="Input sample rate in Hz (after decimation)")
    p.add_argument("--mode", type=str, default="24k",
                   help="Bandwidth mode: 24k,12k,8k,6k,4k")
    return p.parse_args(argv)


def mode_to_cutoff(sample_rate: float, mode: str):
    """Map mode string to audio cutoff in Hz.

    Modes are approximate RF channel widths; we map to ~half-bandwidth
    audio LPF cutoff and clamp to Nyquist. Returning None means pass-through.
    """\

    mode = (mode or "").lower()

    # Target audio cutoffs for nominal ~24 kHz IQ rate
    mapping = {
        "24k": None,        # no extra LPF
        "12k": 6000.0,
        "8k":  4000.0,
        "6k":  3000.0,
        "4k":  2000.0,
    }

    cutoff = mapping.get(mode)
    if cutoff is None:
        return None

    nyq = sample_rate / 2.0
    # If cutoff is too close to or beyond Nyquist, disable filtering
    if cutoff >= 0.9 * nyq:
        return None

    return cutoff


def stream_filter(sample_rate: float, mode: str):
    cutoff = mode_to_cutoff(sample_rate, mode)

    # If no filtering requested, just pass through bytes
    if cutoff is None:
        bufsize = 4096 * 8  # 4096 complex samples * 8 bytes
        stdin = sys.stdin.buffer
        stdout = sys.stdout.buffer
        while True:
            chunk = stdin.read(bufsize)
            if not chunk:
                break
            stdout.write(chunk)
            stdout.flush()
        return

    # Design FIR for the given cutoff
    taps = design_lowpass(sample_rate, cutoff, num_taps=129)
    ntaps = len(taps)
    delay = ntaps - 1

    # State holds the last (ntaps-1) samples between chunks
    state = np.zeros(delay, dtype=np.complex64)

    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    # Process in chunks of complex samples
    samples_per_chunk = 4096
    bytes_per_sample = 8  # 2 * float32

    while True:
        raw = stdin.read(samples_per_chunk * bytes_per_sample)
        if not raw:
            break

        # Convert to complex64 IQ
        data = np.frombuffer(raw, dtype=np.float32)
        if data.size % 2 != 0:
            # Drop the last odd float if we get an incomplete pair
            data = data[:-1]
        if data.size == 0:
            continue

        iq = data.view(np.complex64)

        # Prepend state and filter
        x = np.concatenate((state, iq))
        y = np.convolve(x, taps, mode="valid")  # length = len(x) - ntaps + 1

        # Update state: last (ntaps-1) input samples
        if x.size >= delay:
            state = x[-delay:]
        else:
            # Unusual, but handle very small chunks
            state = x.copy()

        # Write filtered samples as interleaved float32 I,Q
        y_interleaved = np.empty(y.size * 2, dtype=np.float32)
        y_interleaved[0::2] = y.real.astype(np.float32)
        y_interleaved[1::2] = y.imag.astype(np.float32)

        stdout.write(y_interleaved.tobytes())
        stdout.flush()


def main(argv=None):
    args = parse_args(argv)
    try:
        stream_filter(args.rate, args.mode)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
