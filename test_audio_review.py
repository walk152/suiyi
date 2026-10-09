import io
import queue
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from audio_review import (ClipStore, ReviewClip, PlaybackController, ReplayGate,
                          make_audio_clip, encode_wav)


def clip(ident='audio-1', seconds=1, revision=1):
    return ReviewClip(ident, b'\0\0' * int(seconds * 16000), 'Original', 'Translation', revision)


def until(predicate, timeout=2.):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.01)
    return bool(predicate())


class ClipTests(unittest.TestCase):
    def test_store_caps_audio_duration_bytes_and_item_count(self):
        store = ClipStore()
        for index in range(1000):
            store.add(clip(str(index), 8.5))
        self.assertLessEqual(store.total_bytes, 1_920_000)
        self.assertLessEqual(store.seconds, 60)
        self.assertEqual(store.list()[-1].ident, '999')
        self.assertIsNone(store.get('0'))
        tiny = ClipStore(max_seconds=60, max_bytes=32_000, max_clips=3)
        for index in range(10):
            tiny.add(clip(str(index), .2))
        self.assertEqual(len(tiny.list()), 3)
        self.assertLessEqual(tiny.total_bytes, 32_000)
        tiny.clear()
        self.assertEqual(tiny.list(), [])
        self.assertEqual(tiny.total_bytes, 0)

    def test_revision_is_replaced_without_duplicate_or_older_rollback(self):
        store = ClipStore()
        first = clip(revision=1)
        store.add(first)
        store.add(first)
        newer = clip(seconds=2, revision=2)
        store.add(newer)
        store.add(first)
        self.assertEqual(store.list(), [newer])
        self.assertEqual(store.total_bytes, len(newer.pcm16))

    def test_capture_clips_only_final_valid_caption_and_wav_stays_in_memory(self):
        audio = np.linspace(-1, 1, 16000, dtype=np.float32)
        payload = dict(id='audio-1', final=False, source='a', text='b',
                       audio_clip=make_audio_clip(audio), revision=3)
        store = ClipStore()
        self.assertIsNone(store.from_caption(payload))
        payload['final'] = True
        stored = store.from_caption(payload)
        self.assertEqual(stored.seconds, 1.)
        with wave.open(io.BytesIO(encode_wav(stored))) as wav:
            self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getsampwidth()),
                             (1, 16000, 2))
            self.assertEqual(wav.readframes(16000), stored.pcm16)
        payload['audio_clip']['sample_rate'] = 48000
        self.assertIsNone(store.from_caption(payload))

    def test_clip_conversion_is_bounded_finite_and_never_wraps(self):
        audio = np.ones(16000 * 12, dtype=np.float32)
        audio[:5] = [np.nan, np.inf, -np.inf, -2., 2.]
        data = make_audio_clip(audio, continuation=True)
        self.assertTrue(data['truncated'])
        self.assertTrue(data['continuation'])
        self.assertEqual(len(data['pcm16']), 272000)
        self.assertEqual(np.frombuffer(data['pcm16'], dtype='<i2')[:5].tolist(),
                         [0, 32767, -32767, -32767, 32767])


class GateTests(unittest.TestCase):
    def test_ack_requires_actual_reader_reset_and_only_announces_once(self):
        gate = ReplayGate()
        gate.request(True, 'one', now=0)
        self.assertIsNone(gate.take_ready())
        suppressed, reset, generation = gate.reader_state(now=0)
        self.assertTrue(suppressed)
        self.assertTrue(reset)
        self.assertIsNone(gate.take_ready())
        gate.reader_ack(generation)
        self.assertEqual(gate.take_ready(), {'request_id': 'one'})
        self.assertIsNone(gate.take_ready())
        for _ in range(100):
            self.assertEqual(gate.reader_state(now=100), (True, False, generation))

    def test_release_discards_echo_tail_then_resumes_without_stale_ack(self):
        gate = ReplayGate(tail_seconds=.35)
        gate.request(True, 1, now=0)
        _, _, old_generation = gate.reader_state(now=0)
        gate.request(False, 1, now=1)
        gate.reader_ack(old_generation)
        self.assertIsNone(gate.take_ready())
        self.assertTrue(gate.active(now=1.3))
        self.assertTrue(gate.reader_state(now=1.3)[0])
        self.assertFalse(gate.active(now=1.36))
        self.assertFalse(gate.reader_state(now=1.36)[0])
        gate.request(True, 2, now=2)
        self.assertIsNone(gate.take_ready())
        _, reset, generation = gate.reader_state(now=2)
        self.assertTrue(reset)
        gate.reader_ack(generation)
        self.assertEqual(gate.take_ready(), {'request_id': 2})


class PlaybackTests(unittest.TestCase):
    def test_loop_can_stop_immediately_without_waiting_full_excerpt(self):
        began = threading.Event()
        class Player:
            def play(self, pcm, cancelled):
                began.set()
                cancelled.wait(8.5)
        player = PlaybackController(Player)
        token = player.start(clip(seconds=8.5), loop=True)
        self.assertTrue(began.wait(1))
        start = time.monotonic()
        player.stop()
        self.assertTrue(player.wait(.5))
        self.assertLess(time.monotonic() - start, .5)
        kind, payload = player.events.get_nowait()
        self.assertEqual((kind, payload['token']), ('stopped', token))
        self.assertFalse(player.playing)

    def test_switching_clip_serializes_device_playback_and_keeps_tokens(self):
        state = {'active': 0, 'peak': 0}
        began = threading.Event()
        class Player:
            def play(self, pcm, cancelled):
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
                began.set()
                cancelled.wait(.07)
                state['active'] -= 1
        player = PlaybackController(Player, loop_gap=.001)
        first = player.start(clip('one'), loop=True)
        self.assertTrue(began.wait(1))
        second = player.start(clip('two'))
        self.assertTrue(player.wait(1))
        self.assertEqual(state['peak'], 1)
        result = {}
        while not player.events.empty():
            kind, payload = player.events.get_nowait()
            result[payload['token']] = kind
        self.assertEqual(result, {first: 'stopped', second: 'finished'})

    def test_device_failure_is_reported_without_leaving_player_busy(self):
        class Player:
            def play(self, pcm, cancelled):
                raise OSError('test device unavailable')
        player = PlaybackController(Player)
        token = player.start(clip())
        self.assertTrue(player.wait(1))
        kind, payload = player.events.get_nowait()
        self.assertEqual((kind, payload['token']), ('error', token))
        self.assertIn('unavailable', payload['message'])
        self.assertFalse(player.playing)


class EngineGateTests(unittest.TestCase):
    def test_engine_ack_suppresses_vad_and_decode_then_cleanly_resumes(self):
        # All device/model boundaries are fakes: no user's system audio is sampled.
        import engine
        import speech_backend
        import speech_stream
        import learning
        stopped = threading.Event()
        controls = queue.Queue()
        samples = queue.Queue()
        emitted = queue.Queue()
        counts = {'recorded': 0, 'vad': 0, 'decoded': 0}
        class Recorder:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def record(self, numframes=None):
                try: audio = samples.get(timeout=.01)
                except queue.Empty: return np.empty((0, 2), dtype=np.float32)
                counts['recorded'] += 1
                return audio
        class Vad:
            def reset(self): pass
            def __call__(self, audio):
                counts['vad'] += 1
                return 1.
        class Segmenter:
            def __init__(self, **kwargs): self.ident = 0
            def push(self, chunk, probability, now):
                self.ident += 1
                return [speech_stream.AudioJob(self.ident, 1, chunk.copy(), True, now)]
        class Learning:
            def __init__(self, *args): self.profile = 'general'
            def correct(self, text): return text, False
            def observe(self, *args): pass
        def recognize(*args, **kwargs):
            counts['decoded'] += 1
            return SimpleNamespace(text='One safe excerpt.', uncertain=False,
                                   retried=False, review_skipped=False)
        soundcard = SimpleNamespace(get_speaker=lambda ident: SimpleNamespace(id=ident),
            get_microphone=lambda *args, **kwargs: SimpleNamespace(recorder=lambda **kwargs: Recorder()))
        cfg = dict(speaker_id='fake', audio_review=True, idle_release_seconds=180)
        def emit(kind, payload): emitted.put((kind, payload))
        def wait_event(target):
            end = time.monotonic() + 3.
            while time.monotonic() < end:
                try: kind, payload = emitted.get(timeout=.05)
                except queue.Empty: continue
                if kind == 'error': self.fail(payload)
                if kind == target: return payload
            self.fail(f'no {target} event')
        block = np.ones((1024, 2), dtype=np.float32) * .01
        patches = [patch.dict('sys.modules', {'soundcard': soundcard}),
                   patch.object(speech_stream, 'StreamingVad', Vad),
                   patch.object(speech_stream, 'Segmenter', Segmenter),
                   patch.object(speech_backend, 'load_recognizer', return_value=(None, 'cuda', 'fake')),
                   patch.object(speech_backend, 'recognize_detailed', recognize),
                   patch.object(speech_backend, 'prepare_audio', lambda audio: audio),
                   patch.object(learning, 'LearningSession', Learning)]
        for item in patches: item.start()
        worker = threading.Thread(target=engine.capture_audio,
                                  args=(cfg, stopped, emit, None, controls), daemon=True)
        try:
            worker.start()
            samples.put(block)
            first = wait_event('caption')
            self.assertEqual(len(first['audio_clip']['pcm16']), 2048)
            controls.put({'replay_hold': True, 'request_id': 'test'})
            self.assertEqual(wait_event('replay_ready'), {'request_id': 'test'})
            before = counts.copy()
            for _ in range(100): samples.put(block)
            self.assertTrue(until(lambda: counts['recorded'] >= before['recorded'] + 100))
            self.assertEqual(counts['vad'], before['vad'])
            self.assertEqual(counts['decoded'], before['decoded'])
            controls.put({'replay_hold': False, 'request_id': 'test'})
            time.sleep(.5)
            samples.put(block)
            second = wait_event('caption')
            self.assertGreater(counts['decoded'], before['decoded'])
            self.assertNotEqual(first['id'], second['id'])
        finally:
            stopped.set()
            worker.join(2)
            for item in reversed(patches): item.stop()
        self.assertFalse(worker.is_alive())


if __name__ == '__main__':
    unittest.main()
