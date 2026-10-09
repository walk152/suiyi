"""Pause handling without delaying drafts or doing repeat work on silence."""
import unittest

import numpy as np

from speech_stream import Segmenter


class PauseTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.voice = np.ones(1024, dtype=np.float32) * .1
        self.silence = np.zeros(1024, dtype=np.float32)

    def feed(self, segmenter, count, voiced=True):
        events = []
        for _ in range(count):
            self.now += .064
            events.extend(segmenter.push(
                self.voice if voiced else self.silence,
                .9 if voiced else .01,
                now=self.now,
            ))
        return events

    def test_mid_sentence_pause_keeps_id_and_resumes_preview(self):
        segmenter = Segmenter(preview_every=.2)
        before = self.feed(segmenter, 16)
        self.assertEqual(len(before), 1)
        ident = before[0].ident
        self.assertFalse(before[0].final)

        # Eleven capture blocks are 704 ms: enough to end a v0.4 sentence,
        # but a normal breath now keeps the sentence and its subtitle ID.
        paused = self.feed(segmenter, 11, voiced=False)
        self.assertEqual(paused, [])
        resumed = self.feed(segmenter, 1)
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0].ident, ident)
        self.assertFalse(resumed[0].final)
        self.assertGreater(resumed[0].revision, before[0].revision)
        self.assertEqual(len(resumed[0].audio), 28 * 1024)

        finished = self.feed(segmenter, 19, voiced=False)
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0].final)
        self.assertEqual(finished[0].ident, ident)

    def test_early_draft_keeps_requested_timing(self):
        for threshold in (.8, 1.0):
            with self.subTest(threshold=threshold):
                self.now = 0.0
                events = self.feed(Segmenter(preview_after=threshold), 20)
                self.assertFalse(events[0].final)
                self.assertGreaterEqual(events[0].ended, threshold)
                self.assertLess(events[0].ended, threshold + .064)

    def test_one_useful_draft_during_pause_is_not_repeated(self):
        segmenter = Segmenter(preview_after=.8, preview_every=.15)
        self.assertEqual(self.feed(segmenter, 10), [])
        # A short utterance can produce its first draft while waiting for the
        # end pause; the larger end pause does not hold that draft back.
        paused = self.feed(segmenter, 18, voiced=False)
        self.assertEqual(len(paused), 1)
        self.assertFalse(paused[0].final)
        finished = self.feed(segmenter, 1, voiced=False)
        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0].final)

    def test_sufficient_pause_finalizes_and_next_voice_gets_new_id(self):
        segmenter = Segmenter()
        first = self.feed(segmenter, 16)
        self.assertEqual(self.feed(segmenter, 18, voiced=False), [])
        end = self.feed(segmenter, 1, voiced=False)
        self.assertEqual(len(end), 1)
        self.assertTrue(end[0].final)
        self.assertEqual(first[0].ident, end[0].ident)

        self.assertEqual(self.feed(segmenter, 100, voiced=False), [])
        second = self.feed(segmenter, 16)
        self.assertGreater(second[0].ident, first[0].ident)
        self.assertFalse(second[0].continuation)

    def test_silence_never_starts_inference_and_preroll_stays_bounded(self):
        segmenter = Segmenter()
        self.assertEqual(self.feed(segmenter, 2000, voiced=False), [])
        self.assertEqual(segmenter.ident, 0)
        self.assertEqual(segmenter.blocks, [])
        self.assertEqual(len(segmenter.preroll), 5)

    def test_maximum_window_retains_overlap_and_continuation(self):
        segmenter = Segmenter()
        events = self.feed(segmenter, 140)
        finals = [event for event in events if event.final]
        self.assertEqual(len(finals), 1)
        final = finals[0]
        self.assertLessEqual(len(final.audio), int((8.0 + .064) * 16000))
        self.assertGreaterEqual(len(final.audio), 8 * 16000)
        self.assertFalse(final.continuation)
        following = [event for event in events if event.ident > final.ident]
        self.assertTrue(following)
        self.assertTrue(all(event.continuation for event in following))
        self.assertEqual(len(following[0].audio), 16 * 1024)
        np.testing.assert_array_equal(following[0].audio[:10240], final.audio[-10240:])

    def test_explicit_short_pause_setting_remains_supported(self):
        segmenter = Segmenter(silence=.55)
        self.feed(segmenter, 16)
        events = self.feed(segmenter, 9, voiced=False)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].final)


if __name__ == '__main__':
    unittest.main()
