"""Small in-memory audio excerpts and cancellable local Windows playback.

No files, network, recorder or model is opened by this module.  The capture
process sends PCM only for final captions; the UI owns the bounded clip store.
"""
from collections import OrderedDict
from dataclasses import dataclass
import ctypes
import io
import queue
import sys
import threading
import time
import wave

SAMPLE_RATE = 16000
MAX_CLIP_SECONDS = 8.5


def make_audio_clip(audio, continuation=False):
    """Convert one final recognition window to bounded mono PCM, not a new copy of the stream."""
    import numpy as np
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    limit = int(SAMPLE_RATE * MAX_CLIP_SECONDS)
    truncated = len(samples) > limit
    # Keep the start corresponding to the caption. Segmenter normally caps at 8 s.
    samples = samples[:limit]
    samples = np.clip(np.nan_to_num(samples, nan=0., posinf=1., neginf=-1.), -1., 1.)
    pcm = (samples * 32767).astype('<i2').tobytes()
    return dict(pcm16=pcm, sample_rate=SAMPLE_RATE,
                continuation=bool(continuation), truncated=truncated)


@dataclass(frozen=True)
class ReviewClip:
    ident: str
    pcm16: bytes
    source: str = ''
    text: str = ''
    revision: int = 0
    continuation: bool = False
    truncated: bool = False

    @property
    def seconds(self):
        return len(self.pcm16) / (SAMPLE_RATE * 2)

    @property
    def sample_rate(self):
        return SAMPLE_RATE


class ClipStore:
    """At most 60 audio seconds / 1.92 MB by default; old excerpts expire first."""
    def __init__(self, max_seconds=60, max_bytes=1_920_000, max_clips=60):
        self.limit = max(0, min(int(max_bytes), int(max_seconds * SAMPLE_RATE * 2)))
        self.max_clips = max(0, int(max_clips))
        self._clips = OrderedDict()
        self.total_bytes = 0

    @property
    def seconds(self):
        return self.total_bytes / (SAMPLE_RATE * 2)

    def add(self, clip):
        if not isinstance(clip, ReviewClip):
            raise TypeError('clip must be a ReviewClip')
        if not clip.ident or not clip.pcm16 or len(clip.pcm16) % 2:
            return None
        if len(clip.pcm16) > min(self.limit, int(MAX_CLIP_SECONDS * SAMPLE_RATE * 2)):
            return None
        if not self.max_clips:
            return None
        old = self._clips.get(clip.ident)
        if old and old.revision >= clip.revision:
            return old
        if old:
            self.total_bytes -= len(old.pcm16)
        self._clips[clip.ident] = clip
        self.total_bytes += len(clip.pcm16)
        while self.total_bytes > self.limit or len(self._clips) > self.max_clips:
            _, removed = self._clips.popitem(last=False)
            self.total_bytes -= len(removed.pcm16)
        return self._clips.get(clip.ident)

    def from_caption(self, caption):
        data = caption.get('audio_clip')
        if not caption.get('final') or not isinstance(data, dict):
            return None
        pcm = data.get('pcm16')
        if data.get('sample_rate') != SAMPLE_RATE or not isinstance(pcm, bytes):
            return None
        ident = str(caption.get('id', ''))[:100]
        return self.add(ReviewClip(
            ident=ident, pcm16=pcm, source=str(caption.get('source', ''))[:2000],
            text=str(caption.get('text', ''))[:2000], revision=int(caption.get('revision', 0)),
            continuation=bool(data.get('continuation')), truncated=bool(data.get('truncated'))))

    def list(self):
        """Return excerpts oldest first (the newest is list()[-1])."""
        return list(self._clips.values())

    def get(self, ident):
        return self._clips.get(ident)

    def clear(self):
        self._clips.clear()
        self.total_bytes = 0


def encode_wav(clip):
    """Convenience for consumers that need WAV; does not write to disk."""
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(clip.pcm16)
    return stream.getvalue()


class ReplayGate:
    """Coordinate capture flush and main-thread ACK before replay starts.

    request() and take_ready() run on the recognizer thread; reader_state() /
    reader_ack() run on the capture thread. Hold and the short release tail skip
    VAD entirely while still draining the device, so replay cannot transcribe itself.
    """
    def __init__(self, tail_seconds=.35):
        self.tail_seconds = tail_seconds
        self._lock = threading.Lock()
        self._held = False
        self._tail_until = 0.
        self._generation = 0
        self._reader_generation = -1
        self._ready_generation = -1
        self._announced_generation = -1
        self._reader_suppressed = False
        self._request_id = None

    def request(self, held, request_id=None, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            self._generation += 1
            self._request_id = request_id
            self._held = bool(held)
            self._tail_until = 0. if held else now + self.tail_seconds

    def active(self, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            return self._held or now < self._tail_until

    def reader_state(self, now=None):
        """Return (discard_samples, reset_once, generation). ACK after actual reset."""
        now = time.monotonic() if now is None else now
        with self._lock:
            suppressed = self._held or now < self._tail_until
            reset = suppressed and (not self._reader_suppressed or
                                    self._reader_generation != self._generation)
            self._reader_suppressed = suppressed
            if reset:
                self._reader_generation = self._generation
            return suppressed, reset, self._generation

    def reader_ack(self, generation):
        with self._lock:
            if generation == self._generation and self._held:
                self._ready_generation = generation

    def take_ready(self):
        with self._lock:
            if (self._held and self._ready_generation == self._generation and
                    self._announced_generation != self._generation):
                self._announced_generation = self._generation
                return {'request_id': self._request_id}
        return None


class _WindowsPlayer:
    """One cancellable WinMM output handle, confined to the playback worker.

    WinMM avoids extra dependencies and supports in-memory PCM with waveOutReset
    for stopping a loop. No system sounds or another application's audio are stopped.
    """
    def play(self, pcm16, cancelled):
        if sys.platform != 'win32':
            raise OSError('音频回听目前仅支持 Windows')
        from ctypes import wintypes as wt

        class WaveFormat(ctypes.Structure):
            _fields_ = [('wFormatTag', wt.WORD), ('nChannels', wt.WORD),
                        ('nSamplesPerSec', wt.DWORD), ('nAvgBytesPerSec', wt.DWORD),
                        ('nBlockAlign', wt.WORD), ('wBitsPerSample', wt.WORD),
                        ('cbSize', wt.WORD)]

        class WaveHeader(ctypes.Structure):
            _fields_ = [('lpData', ctypes.c_void_p), ('dwBufferLength', wt.DWORD),
                        ('dwBytesRecorded', wt.DWORD), ('dwUser', ctypes.c_size_t),
                        ('dwFlags', wt.DWORD), ('dwLoops', wt.DWORD),
                        ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_size_t)]

        library = ctypes.WinDLL('winmm')
        handle = wt.HANDLE()
        fmt = WaveFormat(1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16, 0)
        library.waveOutOpen.argtypes = [ctypes.POINTER(wt.HANDLE), wt.UINT,
                                        ctypes.POINTER(WaveFormat), ctypes.c_size_t,
                                        ctypes.c_size_t, wt.DWORD]
        library.waveOutOpen.restype = wt.UINT
        for name in ('waveOutPrepareHeader', 'waveOutWrite', 'waveOutUnprepareHeader'):
            fn = getattr(library, name)
            fn.argtypes = [wt.HANDLE, ctypes.POINTER(WaveHeader), wt.UINT]
            fn.restype = wt.UINT
        for name in ('waveOutReset', 'waveOutClose'):
            fn = getattr(library, name)
            fn.argtypes = [wt.HANDLE]
            fn.restype = wt.UINT

        def check(code, action):
            if code:
                raise OSError(f'音频回听{action}失败（Windows {code}）')

        if cancelled.is_set():
            return
        check(library.waveOutOpen(ctypes.byref(handle), 0xFFFFFFFF, ctypes.byref(fmt),
                                 0, 0, 0), '打开设备')
        buffer = ctypes.create_string_buffer(pcm16)
        header = WaveHeader(ctypes.addressof(buffer), len(pcm16), 0, 0, 0, 0, None, 0)
        prepared = False
        try:
            check(library.waveOutPrepareHeader(handle, ctypes.byref(header),
                                              ctypes.sizeof(header)), '准备')
            prepared = True
            if not cancelled.is_set():
                check(library.waveOutWrite(handle, ctypes.byref(header),
                                           ctypes.sizeof(header)), '播放')
                deadline = time.monotonic() + len(pcm16) / (SAMPLE_RATE * 2) + 3.
                while not header.dwFlags & 1:  # WHDR_DONE
                    if cancelled.wait(.025):
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError('回听设备没有及时完成播放，请重新选择输出设备。')
        finally:
            # Reset returns queued buffers before their Python backing memory is freed.
            library.waveOutReset(handle)
            if prepared:
                library.waveOutUnprepareHeader(handle, ctypes.byref(header), ctypes.sizeof(header))
            library.waveOutClose(handle)


class PlaybackController:
    """A single worker; completion events are polled by Tk, never callbacks into Tk.

    start() cancels the previous excerpt and returns a generation token. UI must
    ignore completion events whose token is no longer the active generation.
    Only release the capture replay hold after receiving the active completion.
    """
    def __init__(self, player_factory=None, loop_gap=.35):
        self.events = queue.Queue()
        self._player_factory = player_factory or _WindowsPlayer
        self._loop_gap = max(0., float(loop_gap))
        self._lock = threading.Lock()
        self._pending = None
        self._cancelled = None
        self._thread = None
        self._token = 0

    def start(self, clip, loop=False):
        if not isinstance(clip, ReviewClip) or not clip.pcm16:
            raise ValueError('还没有可回听的声音片段')
        with self._lock:
            self._token += 1
            token = self._token
            if self._cancelled:
                self._cancelled.set()
            if self._pending:
                self.events.put(('stopped', {'token': self._pending[0]}))
            self._pending = (token, clip, bool(loop))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name='suiyi-replay')
                self._thread.start()
            return token

    def stop(self):
        with self._lock:
            if self._pending:
                self.events.put(('stopped', {'token': self._pending[0]}))
                self._pending = None
            if self._cancelled:
                self._cancelled.set()

    def wait(self, timeout=1.):
        """For shutdown/test callers, not required in the UI event handler."""
        thread = self._thread
        if thread:
            thread.join(timeout)
        return thread is None or not thread.is_alive()

    @property
    def playing(self):
        with self._lock:
            return self._pending is not None or self._cancelled is not None

    def _run(self):
        while True:
            with self._lock:
                item, self._pending = self._pending, None
                if item is None:
                    self._thread = None
                    return
                token, clip, loop = item
                cancelled = self._cancelled = threading.Event()
            kind, payload = 'finished', {'token': token, 'ident': clip.ident}
            try:
                player = self._player_factory()
                while not cancelled.is_set():
                    player.play(clip.pcm16, cancelled)
                    if not loop or cancelled.wait(self._loop_gap):
                        break
                if cancelled.is_set():
                    kind = 'stopped'
            except Exception as exc:
                kind, payload['message'] = 'error', str(exc)
            finally:
                with self._lock:
                    self._cancelled = None
                self.events.put((kind, payload))
