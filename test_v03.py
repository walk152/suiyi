import unittest, tempfile, time, queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from speech_backend import recognize_detailed, normalize_hint, prepare_audio
from speech_stream import AudioJob, AudioFramer, StreamingVad
from lexicon import lookup, word_at
from runtime_paths import BUNDLE_ROOT

has_dictionary=unittest.skipUnless((BUNDLE_ROOT/'dictionary/ecdict.sqlite3').is_file(), 'Optional ECDICT dataset: run tools/prepare_dictionary.py')

def segment(text='Hello.',score=-.2,no_speech=.01):
    return SimpleNamespace(text=text,avg_logprob=score,no_speech_prob=no_speech,compression_ratio=1.1)

class RecognitionTests(unittest.TestCase):
    def job(self,final=True):return AudioJob(1,1,np.ones(32000,dtype=np.float32)*.01,final,time.monotonic())
    def test_names_are_hotwords_without_forced_replacement(self):
        model=Mock();model.transcribe.return_value=([segment('Different words.')],None)
        result=recognize_detailed(model,self.job(),hint='Sotheby， Vertin, Sotheby')
        self.assertEqual(model.transcribe.call_args.kwargs['hotwords'],'Sotheby, Vertin')
        self.assertEqual(result.text,'Different words.')
    def test_uncertain_final_retries_once_and_retains_better_result(self):
        model=Mock();model.transcribe.side_effect=[([segment('first',-.95)],None),([segment('clearer',-.4)],None)]
        result=recognize_detailed(model,self.job())
        self.assertEqual(model.transcribe.call_count,2);self.assertEqual(result.text,'clearer');self.assertTrue(result.retried)
    def test_draft_never_retries_and_low_confidence_marked(self):
        model=Mock();model.transcribe.return_value=([segment('unclear',-1.25)],None)
        result=recognize_detailed(model,self.job(False))
        self.assertEqual(model.transcribe.call_count,1);self.assertTrue(result.uncertain);self.assertEqual(result.text,'unclear')
    def test_silence_never_invokes_decoder(self):
        model=Mock();job=self.job();job.audio.fill(0)
        self.assertEqual(recognize_detailed(model,job,hint='Vertin').text,'');model.transcribe.assert_not_called()
    def test_gain_bounded_and_finite(self):
        audio=np.ones(16000,dtype=np.float32)*.001
        self.assertLessEqual(float(prepare_audio(audio).max()),.004001)
        self.assertTrue(np.all(np.isfinite(prepare_audio(np.array([np.nan,np.inf,0])))))
    def test_long_hints_bounded(self):
        self.assertLessEqual(len(normalize_hint(','.join(str(i)*100 for i in range(50)))),500)

class IdleTests(unittest.TestCase):
    def test_suspend_discards_backlog_and_preserves_new_tail(self):
        f=AudioFramer();f.push(np.ones(800),now=0)
        frames,reset=f.push(np.ones(160000),now=60)
        self.assertTrue(reset);self.assertEqual(len(frames),4);self.assertLess(len(f.tail),1024)
    def test_normal_frames_not_lost(self):
        f=AudioFramer();out=[]
        for i in range(20):
            frames,reset=f.push(np.arange(i*160,(i+1)*160),i*.01);out+=frames
            self.assertFalse(reset)
        np.testing.assert_array_equal(np.concatenate(out+[f.tail]),np.arange(3200))
    def test_digital_silence_does_not_run_neural_vad(self):
        vad=StreamingVad.__new__(StreamingVad);vad.session=Mock();vad.reset()
        for _ in range(100):self.assertEqual(vad(np.zeros(1024,dtype=np.float32)),0)
        vad.session.run.assert_not_called()

class DictionaryTests(unittest.TestCase):
    def test_word_boundary_and_contraction(self):
        self.assertEqual(word_at("We can't wait.",5),"can't")
        self.assertEqual(word_at('Hello 世界',7),'')
    @has_dictionary
    def test_real_lookup_and_inflection(self):
        self.assertTrue(lookup('rain')['entries'][0]['translation'])
        self.assertTrue(any(x['word'].casefold()=='go' for x in lookup('went')['entries']))
    @has_dictionary
    def test_unknown_name_is_not_invented(self):
        r=lookup('zxqnotarealpersonxyz');self.assertEqual(r['entries'],[]);self.assertIn('未收录',r['message'])
    @has_dictionary
    def test_sql_input_and_long_text_safe(self):
        self.assertFalse(lookup("'; DROP TABLE entries;--")['entries'])
        self.assertTrue(lookup('rain')['entries'])
        self.assertIn('最多',lookup('word '*100)['message'])

if __name__=='__main__':unittest.main()
