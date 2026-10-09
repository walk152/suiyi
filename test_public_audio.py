"""PCM fidelity and no-PyAV import tests for the public installer audio path."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

import numpy as np

from public_audio import UnsupportedAudioError, decode_audio, pad_or_trim


def wav_bytes(values, width=2, channels=1, rate=16000):
    payload = io.BytesIO()
    with wave.open(payload, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(values)
    return payload.getvalue()


class PcmAudioTests(unittest.TestCase):
    def test_signed_pcm_depths_preserve_full_scale_and_zero(self):
        for width in (2, 3, 4):
            with self.subTest(width=width):
                maximum = (1 << (8 * width - 1)) - 1
                values = [-maximum - 1, 0, maximum]
                raw = b"".join(value.to_bytes(width, "little", signed=True) for value in values)
                audio = decode_audio(io.BytesIO(wav_bytes(raw, width=width)))
                self.assertEqual(audio.dtype, np.float32)
                np.testing.assert_allclose(audio, [-1.0, 0.0, maximum / (maximum + 1)], atol=1e-7)

    def test_unsigned_eight_bit_has_correct_silence(self):
        audio = decode_audio(io.BytesIO(wav_bytes(bytes([0, 128, 255]), width=1)))
        np.testing.assert_array_equal(audio, [-1.0, 0.0, 127 / 128])

    def test_stereo_channels_and_mono_downmix(self):
        data = wav_bytes(np.array([[8192, -8192], [16384, 0]], dtype="<i2").tobytes(), channels=2)
        left, right = decode_audio(io.BytesIO(data), split_stereo=True)
        np.testing.assert_array_equal(left, [0.25, 0.5])
        np.testing.assert_array_equal(right, [-0.25, 0])
        np.testing.assert_array_equal(decode_audio(io.BytesIO(data)), [0, 0.25])
        self.assertTrue(left.flags.c_contiguous)

    def test_mono_split_returns_independent_channels(self):
        left, right = decode_audio(io.BytesIO(wav_bytes(b"\0\0\0\x40")), split_stereo=True)
        left[0] = 1
        np.testing.assert_array_equal(right, [0, 0.5])

    def test_path_and_caller_owned_stream(self):
        data = wav_bytes(b"\0\0\0\x40")
        stream = io.BytesIO(data)
        decode_audio(stream)
        self.assertFalse(stream.closed)
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "sample.wav"
            filename.write_bytes(data)
            np.testing.assert_array_equal(decode_audio(filename), [0, 0.5])

    def test_rejects_resampling_instead_of_changing_audio_silently(self):
        with self.assertRaisesRegex(UnsupportedAudioError, "does not resample"):
            decode_audio(io.BytesIO(wav_bytes(b"\0\0", rate=48000)))

    def test_rejects_unsupported_container_truncation_empty_and_multichannel(self):
        samples = [b"ID3 unsupported MP3", wav_bytes(b"\0\0")[:-1], wav_bytes(b""),
                   wav_bytes(b"\0" * 6, channels=3)]
        for data in samples:
            with self.subTest(size=len(data)), self.assertRaises(UnsupportedAudioError):
                decode_audio(io.BytesIO(data))

    def test_pad_and_trim_arbitrary_axis_and_dtype(self):
        data = np.arange(12, dtype=np.float32).reshape(2, 3, 2)
        padded = pad_or_trim(data, 5, axis=1)
        self.assertEqual(padded.shape, (2, 5, 2))
        self.assertEqual(padded.dtype, data.dtype)
        np.testing.assert_array_equal(padded[:, :3, :], data)
        np.testing.assert_array_equal(padded[:, 3:, :], 0)
        np.testing.assert_array_equal(pad_or_trim(data, 1, axis=-2), data[:, :1, :])
        self.assertIs(pad_or_trim(data, 3, axis=1), data)

    def test_invalid_feature_length_and_axis(self):
        with self.assertRaises(ValueError):
            pad_or_trim(np.zeros((2, 3)), -1)
        with self.assertRaises(ValueError):
            pad_or_trim(np.zeros((2, 3)), axis=4)

    def test_upstream_and_runtime_hook_import_without_av(self):
        # Fresh interpreter ensures another test cannot preload the forbidden decoder.
        code = """
import importlib.abc
import runpy
import sys
class NoPyAV(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'av' or fullname.startswith('av.'):
            raise AssertionError('Public runtime attempted to import PyAV: ' + fullname)
sys.meta_path.insert(0, NoPyAV())
runpy.run_path('tools/public_audio_hook.py')
from public_audio import install_faster_whisper_audio, decode_audio, pad_or_trim
first = install_faster_whisper_audio()
assert install_faster_whisper_audio() is first
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model
from faster_whisper.transcribe import decode_audio as decoder, pad_or_trim as padder
assert decoder is decode_audio and padder is pad_or_trim
assert not any(name == 'av' or name.startswith('av.') for name in sys.modules)
print('WhisperModel and VAD imported without PyAV')
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                text=True, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
