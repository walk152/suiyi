"""Bounded, revisable speech snapshots with independent capture and recognition."""
from collections import OrderedDict, deque
from dataclasses import dataclass
import threading, time, queue, re
import numpy as np
from public_audio import install_faster_whisper_audio
install_faster_whisper_audio()

@dataclass
class AudioJob:
    ident: int
    revision: int
    audio: np.ndarray
    final: bool
    ended: float
    continuation: bool = False

class StreamingVad:
    """Stateful Silero v6 on the capture thread, 16 kHz / 512 samples."""
    def __init__(self):
        from faster_whisper.vad import get_vad_model
        self.session = get_vad_model().session
        self.reset()

    def reset(self):
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = self.h.copy()
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.silent_samples=0

    def __call__(self, audio):
        # Digital silence needs no neural inference; reset stale recurrent state once.
        if np.max(np.abs(audio),initial=0)<1e-5:
            self.silent_samples+=len(audio)
            if self.silent_samples>=16000:
                self.h.fill(0);self.c.fill(0);self.context.fill(0)
            return 0.0
        self.silent_samples=0
        probability = 0.0
        for i in range(0, len(audio), 512):
            block = audio[i:i+512]
            if len(block) != 512:
                raise ValueError('VAD requires multiples of 512 samples')
            inputs = np.concatenate((self.context, block[None,:]), axis=1)
            scores, self.h, self.c = self.session.run(None, {'input': inputs, 'h': self.h, 'c': self.c})
            self.context = block[-64:][None,:].copy()
            probability = max(probability, float(np.max(scores)))
        return probability

class AudioFramer:
    """Bound audio left after suspend; never process minutes of synthetic silence."""
    def __init__(self):
        self.tail=np.empty(0,dtype=np.float32)
        self.last=None

    def push(self, audio, now):
        gap=self.last is not None and now-self.last>1.5
        self.last=now
        audio=np.asarray(audio,dtype=np.float32)
        reset=gap or len(audio)>16000
        if reset:
            self.tail=np.empty(0,dtype=np.float32)
            audio=audio[-4096:]
        samples=np.concatenate((self.tail,audio))
        end=len(samples)//1024*1024
        frames=[samples[i:i+1024] for i in range(0,end,1024)]
        self.tail=samples[end:].copy()
        return frames,reset

class Segmenter:
    """Emit an early draft, then revise the same ID until a pause or bounded cut."""
    def __init__(self, preview_after=1.0, preview_every=.85, silence=1.2, maximum=8.0):
        self.preview_after = preview_after
        self.preview_every = preview_every
        self.silence_limit = silence
        self.maximum = maximum
        self.preroll = deque(maxlen=5)
        self.blocks = []
        self.duration = self.quiet = 0.0
        self.next_preview = preview_after
        self.ident = 0
        self.revision = 0
        self.continuation = False
        self.preview_dirty = False

    def push(self, block, probability, now=None):
        now = time.monotonic() if now is None else now
        seconds = len(block)/16000
        jobs = []
        if not self.blocks:
            if probability < .5:
                self.preroll.append(block.copy())
                return jobs
            self.ident += 1
            self.revision = 0
            self.blocks = list(self.preroll)
            self.preroll.clear()
            self.duration = sum(len(b) for b in self.blocks)/16000
        self.blocks.append(block.copy())
        self.duration += seconds
        self.quiet = self.quiet + seconds if probability < .32 else 0.0
        if probability >= .32:
            self.preview_dirty = True
        final = self.quiet >= self.silence_limit or self.duration >= self.maximum
        # A brief pause may complete a useful draft, but extra silence alone
        # must not repeatedly ask the recognizer to transcribe the same speech.
        preview_due = self.duration >= self.next_preview and self.preview_dirty
        if final or preview_due:
            self.revision += 1
            audio = np.concatenate(self.blocks)
            jobs.append(AudioJob(self.ident, self.revision, audio, final, now, self.continuation))
            self.next_preview = self.duration+self.preview_every
            self.preview_dirty = False
            if final:
                continuous = self.quiet < self.silence_limit
                tail = audio[-10240:].copy() if continuous else None
                self.blocks = []
                self.duration = self.quiet = 0.0
                self.next_preview = self.preview_after
                self.continuation = continuous
                if continuous:
                    self.ident += 1
                    self.revision = 0
                    self.blocks = [tail]
                    self.duration = len(tail)/16000
        return jobs

class PendingAudio:
    """Only newest snapshot per utterance. Keep age and count bounded."""
    def __init__(self, capacity=3, max_age=3.0):
        self.capacity, self.max_age = capacity, max_age
        self.items = OrderedDict()
        self.cv = threading.Condition()
        self.dropped = 0

    def put(self, job):
        with self.cv:
            old = self.items.get(job.ident)
            if old and (old.final or old.revision >= job.revision):
                return
            self.items[job.ident] = job
            while len(self.items) > self.capacity:
                self.items.popitem(last=False)
                self.dropped += 1
            self.cv.notify()

    def get(self, timeout=.25, now=None, max_age=None):
        with self.cv:
            if not self.items:
                self.cv.wait(timeout)
            current = time.monotonic() if now is None else now
            while self.items:
                _, job = self.items.popitem(last=False)
                if current-job.ended <= (self.max_age if max_age is None else max_age):
                    return job
                self.dropped += 1
            raise queue.Empty()

    def drop_count(self):
        with self.cv:
            count, self.dropped = self.dropped, 0
            return count

    def has_other(self, ident):
        with self.cv:
            return any(key!=ident for key in self.items)

    def clear(self):
        with self.cv:
            self.items.clear()

def trim_overlap(previous, current, continuation):
    """Remove a repeated prefix only across explicitly overlapping audio windows."""
    if not continuation:
        return current
    old, new = previous.split(), current.split()
    clean = lambda s: re.sub(r'[^\w]', '', s).casefold()
    for n in range(min(14, len(old), len(new)), 1, -1):
        if [clean(x) for x in old[-n:]] == [clean(x) for x in new[:n]]:
            return ' '.join(new[n:])
    return current
