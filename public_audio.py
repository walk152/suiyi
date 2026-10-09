"""Small audio adapter for Suiyi's local capture and PCM WAV self-tests.

Live recognition passes 16 kHz float32 NumPy arrays to faster-whisper directly;
that upstream path never calls a file decoder. This adapter intentionally does
not implement MP3, AAC, video demuxing, encoding, or sample-rate conversion.
It must be installed before importing any faster_whisper module.
"""
from __future__ import annotations

import importlib.machinery
import os
import sys
import types
import wave

import numpy as np


class UnsupportedAudioError(ValueError):
    """The input cannot be decoded without changing the PCM-only contract."""


def decode_audio(input_file, sampling_rate: int = 16000, split_stereo: bool = False):
    """Read integer PCM WAV into float32 without resampling.

    Accepts a path or a binary file object at its WAV header. The WAV must have
    one or two channels and the requested sampling rate. Stereo is averaged
    for mono output; ``split_stereo=True`` returns a pair of channels (a mono
    source is copied into both). Unsupported formats fail explicitly.
    """
    if isinstance(sampling_rate, bool) or not isinstance(sampling_rate, int) or sampling_rate <= 0:
        raise ValueError("sampling_rate must be a positive integer")
    source = os.fspath(input_file) if isinstance(input_file, os.PathLike) else input_file
    try:
        with wave.open(source, "rb") as stream:
            channels = stream.getnchannels()
            width = stream.getsampwidth()
            rate = stream.getframerate()
            frames = stream.getnframes()
            if stream.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
                raise UnsupportedAudioError("Only 8/16/24/32-bit integer PCM WAV is supported")
            if channels not in (1, 2):
                raise UnsupportedAudioError("PCM WAV must have one or two channels")
            if rate != sampling_rate:
                raise UnsupportedAudioError(
                    f"PCM WAV is {rate} Hz; expected {sampling_rate} Hz. "
                    "This build does not resample audio files."
                )
            raw = stream.readframes(frames)
            if len(raw) != frames * channels * width:
                raise UnsupportedAudioError("Truncated PCM WAV audio data")
    except (wave.Error, EOFError) as exc:
        raise UnsupportedAudioError(
            "Only uncompressed integer PCM WAV is supported; compressed audio and video files are not supported"
        ) from exc
    if not frames:
        raise UnsupportedAudioError("PCM WAV contains no audio frames")
    if width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 3:
        octets = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = octets[:, 0] | (octets[:, 1] << 8) | (octets[:, 2] << 16)
        values = (values ^ 0x800000) - 0x800000
        samples = values.astype(np.float32) / 8388608.0
    else:
        samples = np.frombuffer(raw, dtype="<i2" if width == 2 else "<i4").astype(np.float32)
        samples /= float(1 << (width * 8 - 1))
    samples = samples.reshape(-1, channels)
    if split_stereo:
        return samples[:, 0].copy(), samples[:, channels - 1].copy()
    return np.ascontiguousarray(samples.mean(axis=1), dtype=np.float32)


def pad_or_trim(array, length: int = 3000, *, axis: int = -1):
    """Fit one feature dimension, preserving dtype and every other dimension."""
    if isinstance(length, bool) or not isinstance(length, int) or length < 0:
        raise ValueError("length must be a non-negative integer")
    if not -array.ndim <= axis < array.ndim:
        raise ValueError("axis is outside the array dimensions")
    axis %= array.ndim
    if array.shape[axis] > length:
        index = [slice(None)] * array.ndim
        index[axis] = slice(0, length)
        return array[tuple(index)]
    if array.shape[axis] < length:
        padding = [(0, 0)] * array.ndim
        padding[axis] = (0, length - array.shape[axis])
        return np.pad(array, padding, mode="constant")
    return array


def install_faster_whisper_audio():
    """Register the PCM adapter without editing the installed upstream package.

    A late registration would leave references to the old decoder in upstream
    modules, so it is rejected instead of silently mixing audio backends.
    """
    name = "faster_whisper.audio"
    existing = sys.modules.get(name)
    if existing is not None:
        if getattr(existing, "_suiyi_pcm_adapter", False):
            return existing
        raise RuntimeError("Install Suiyi's PCM adapter before importing faster_whisper")
    if "faster_whisper.transcribe" in sys.modules:
        raise RuntimeError("Install Suiyi's PCM adapter before importing faster_whisper.transcribe")
    module = types.ModuleType(name, "Suiyi PCM WAV adapter; compressed file decoding is unavailable.")
    module.__file__ = __file__
    module.__package__ = "faster_whisper"
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    module.__all__ = ["decode_audio", "pad_or_trim"]
    module._suiyi_pcm_adapter = True
    module.decode_audio = decode_audio
    module.pad_or_trim = pad_or_trim
    sys.modules[name] = module
    parent = sys.modules.get("faster_whisper")
    if parent is not None:
        parent.audio = module
    return module
