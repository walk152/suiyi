import unittest, queue
import numpy as np
from speech_stream import Segmenter, PendingAudio, AudioJob, trim_overlap
from captions import CaptionHistory, visible_lines
from core import caption_rect

class StreamingTests(unittest.TestCase):
    def job(self, ident=1, revision=1, final=False, ended=100):
        return AudioJob(ident,revision,np.zeros(1024,dtype=np.float32),final,ended)

    def test_continuous_speech_emits_before_old_six_second_wait(self):
        s=Segmenter();events=[]
        for i in range(30):
            events.extend(s.push(np.ones(1024,dtype=np.float32),.9,now=i*.064))
        self.assertTrue(events)
        self.assertFalse(events[0].final)
        self.assertLess(events[0].ended,1.3)

    def test_pause_finalizes_same_id(self):
        s=Segmenter();events=[]
        for i in range(25):events+=s.push(np.ones(1024),.9,now=i*.064)
        for i in range(19):events+=s.push(np.zeros(1024),.01,now=2+i*.064)
        self.assertTrue(events[-1].final)
        self.assertEqual(events[0].ident,events[-1].ident)
        self.assertGreater(events[-1].revision,events[0].revision)

    def test_music_or_silence_without_voice_does_not_start(self):
        s=Segmenter()
        for _ in range(200):self.assertEqual(s.push(np.ones(1024)*.05,.1),[])
        self.assertEqual(s.blocks,[])

    def test_latest_snapshot_replaces_old_work(self):
        q=PendingAudio()
        for rev in range(1,10):q.put(self.job(revision=rev))
        self.assertEqual(q.get(now=101).revision,9)
        with self.assertRaises(queue.Empty):q.get(timeout=0,now=101)

    def test_final_cannot_be_replaced_by_partial(self):
        q=PendingAudio();q.put(self.job(revision=2,final=True));q.put(self.job(revision=3))
        self.assertTrue(q.get(now=101).final)

    def test_backlog_count_and_age_bounded(self):
        q=PendingAudio(capacity=2,max_age=3)
        for i in range(4):q.put(self.job(ident=i))
        self.assertEqual(q.drop_count(),2)
        with self.assertRaises(queue.Empty):q.get(timeout=0,now=104)
        self.assertEqual(q.drop_count(),2)

    def test_overlap_only_across_forced_audio_boundary(self):
        a,b='We need to leave now.','leave now, before the rain starts.'
        self.assertEqual(trim_overlap(a,b,True),'before the rain starts.')
        self.assertEqual(trim_overlap(a,b,False),b)

    def test_history_revises_one_paragraph_preserving_others(self):
        h=CaptionHistory()
        h.update(dict(id='a',text='Earlier sentence.',source='',final=True),now=1)
        h.update(dict(id='b',text='We need',source='',final=False,revision=1),now=2)
        h.update(dict(id='b',text='We need to leave.',source='',final=True,revision=2),now=3)
        self.assertEqual(len(h.records),2)
        self.assertEqual(h.recent(3,now=4)[-1]['text'],'We need to leave.')
        self.assertFalse(h.update(dict(id='b',text='old',final=False,revision=1),now=4))

    def test_history_bounded_and_expired(self):
        h=CaptionHistory(limit=4)
        for i in range(20):h.update(dict(text=str(i),source=''),now=i)
        self.assertEqual(len(h.records),4)
        self.assertEqual(len(h.recent(3,now=20)),3)
        self.assertEqual(h.recent(3,now=60),[])

    def test_three_paragraphs_are_simultaneously_visible(self):
        records=[dict(text=t,final=True) for t in ['One.','Two.','Three.']]
        lines,colors,total=visible_lines(records,100,6,len)
        self.assertEqual(total,3)
        self.assertEqual(lines,['› One.','› Two.','› Three.'])

    def test_small_area_shows_newest_but_keeps_full_history(self):
        records=[dict(text=t,final=True) for t in ['One.','Two.','Three.']]
        lines,_,total=visible_lines(records,100,1,len)
        self.assertEqual(lines,['› Three.']);self.assertEqual(total,3)
        self.assertEqual(len(records),3)

    def test_a_multiple_rows_respect_screen_bottom(self):
        r=caption_rect('A',[100,200,800,800],None,[0,0,1000,1000],30,6)
        self.assertEqual(r,[100,806,800,990])
        r=caption_rect('A',[100,200,800,950],None,[0,0,1000,1000],30,6)
        self.assertEqual(r,[100,956,800,990])

if __name__=='__main__':unittest.main()
