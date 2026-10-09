import unittest,tempfile,time
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from learning import LearningStore,LearningSession,catalog
from speech_backend import recognize_detailed
from speech_stream import AudioJob,PendingAudio
from test_v03 import segment

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=LearningStore(Path(self.temp.name)/'memory.db')
        self.session=LearningSession('1999','en',self.store)

    def test_scoped_durable_reversible_sentence_memory(self):
        self.store.remember('1999','en','sentence','Hello, Sinetto!','Hello, Sonetto!')
        self.session.reload()
        self.assertEqual(self.session.correct('hello sinetto.'),('Hello, Sonetto!',True))
        self.assertIn('Sonetto',self.session.hint())
        for text in ['Hello Sinetto and Regulus','Sinetto','No hello Sinetto']:
            self.assertEqual(self.session.correct(text),(text,False))
        self.assertFalse(LearningSession('general','en',self.store).correct('hello sinetto')[1])
        self.assertFalse(LearningSession('1999','zh',self.store).correct('hello sinetto')[1])
        row=self.store.rows('1999')[0];self.store.forget('1999','en',row);self.session.reload()
        self.assertFalse(self.session.correct('hello sinetto')[1])
        self.assertNotIn('Sonetto',self.session.hint())

    def test_catalog_bounded_hints_and_no_ordinary_word_injection(self):
        self.assertEqual(len(catalog()),140)
        hints=self.session.hint();self.assertEqual(hints,'');self.assertLessEqual(len(hints),400)
        self.assertNotIn('APPLe',hints);self.assertNotIn('APPLe',self.session.candidates('We ate an apple.'))
        self.assertIn('Sonetto',self.session.candidates('Hello, Sinetto.'))
        self.assertIn('Kakania',self.session.candidates('Cockania, did Isolde speak to Matilda?'))
        self.assertIn('Vertin',self.session.candidates('Sonetto, ask Verdon to wait.'))
        self.assertEqual(LearningSession('general','en',self.store).hint(),'')
        self.assertEqual(LearningSession('1999','zh',self.store).hint(),'')

    def test_observation_is_ephemeral_and_uncertain_not_learned(self):
        self.session.observe('Kakania',False);self.assertEqual(self.session.recent,[])
        self.session.observe('Kakania');self.assertIn('Kakania',self.session.hint())
        self.assertEqual(self.store.rows('1999'),[])
        self.assertNotIn('Kakania',LearningSession('1999','en',self.store).hint())

    def test_explicit_name_survives_restart(self):
        self.store.remember('1999','en','name','','Kakania')
        self.assertIn('Kakania',LearningSession('1999','en',self.store).hint())

    def test_review_backpressure(self):
        job=AudioJob(1,1,np.ones(32000,dtype=np.float32)*.1,True,time.monotonic())
        model=Mock();model.transcribe.return_value=([segment('unclear',-.95)],None)
        result=recognize_detailed(model,job,can_review=lambda:False)
        self.assertTrue(result.review_skipped);self.assertFalse(result.retried)
        self.assertEqual(model.transcribe.call_count,1)
        pending=PendingAudio();pending.put(job);self.assertFalse(pending.has_other(1))
        pending.put(AudioJob(2,1,job.audio,False,time.monotonic()));self.assertTrue(pending.has_other(1))

    def test_name_candidate_redecoded_not_text_replaced(self):
        job=AudioJob(1,1,np.ones(32000,dtype=np.float32)*.1,True,time.monotonic())
        model=Mock();model.transcribe.side_effect=[([segment('Hello Sinetto',-.4)],None),([segment('Hello Sonetto',-.2)],None)]
        result=recognize_detailed(model,job,learning=self.session)
        self.assertEqual(result.text,'Hello Sonetto');self.assertTrue(result.retried)
        self.assertTrue(model.transcribe.call_args.kwargs['hotwords'].startswith('Sonetto'))

if __name__=='__main__':unittest.main()
