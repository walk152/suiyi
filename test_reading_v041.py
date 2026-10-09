import unittest
from reading import ReadingPager,reading_seconds

def record(ident,text,final=True,revision=1):
    return dict(id=ident,text=text,final=final,revision=revision,source=text)

class ReadingTests(unittest.TestCase):
    def test_long_sentence_starts_at_beginning_then_all_pages(self):
        p=ReadingPager();p.push(record('a','one two three four five six seven eight nine ten eleven twelve'))
        pages=[]
        for now in range(0,40,4):
            lines,_,_=p.view(17,1,len,now=now,keep=1)
            if lines and (not pages or pages[-1]!=lines[0]):pages.append(lines[0])
        joined=' '.join(pages).replace('› ','')
        self.assertEqual(joined,'one two three four five six seven eight nine ten eleven twelve')

    def test_incoming_sentence_does_not_evict_unread_current_page(self):
        p=ReadingPager();p.push(record('a','An earlier sentence.'))
        first=p.view(80,1,len,now=0)[0]
        p.push(record('b','A new sentence.'))
        self.assertEqual(p.view(80,1,len,now=1)[0],first)
        self.assertEqual(p.view(80,1,len,now=4)[0],['› A new sentence.'])

    def test_partial_final_lost_does_not_block_newer_sentence(self):
        p=ReadingPager();p.push(record('a','hello',False));p.view(80,1,len,now=0)
        p.push(record('b','world'));self.assertEqual(p.view(80,1,len,now=4)[0],['› world'])

    def test_unchanged_revisions_do_not_reset_deadline(self):
        p=ReadingPager();p.push(record('a','one two three four five six',False));p.view(13,1,len,now=0)
        deadline=p.deadline
        for i in range(1,3):
            p.push(record('a','one two three four five six',False,i+1));p.view(13,1,len,now=i)
        self.assertEqual(p.deadline,deadline)
        self.assertEqual(p.view(13,1,len,now=4)[0],['› three four'])

    def test_late_insert_inside_displayed_page_is_not_skipped(self):
        p=ReadingPager();p.push(record('a','alpha beta',False));p.view(100,1,len,now=0)
        p.push(record('a','alpha brand new beta gamma',True,2))
        self.assertEqual(p.view(100,1,len,now=4)[0],['› alpha brand new beta gamma'])
        self.assertGreater(p.deadline,4)

    def test_append_after_consumed_boundary_stays_available(self):
        p=ReadingPager();p.push(record('a','alpha beta',False));p.view(100,1,len,now=0)
        p.push(record('a','alpha beta gamma delta',True,2))
        self.assertEqual(p.view(100,1,len,now=4)[0],['› gamma delta'])

    def test_pause_freezes_text_and_preserves_for_more_than_35_seconds(self):
        p=ReadingPager();p.push(record('a','one two three four five six',False));first=p.view(13,1,len,now=0)[0]
        p.pause(now=1);p.push(record('a','One, two, three, four, five, six.',True,2));p.push(record('b','new sentence'))
        self.assertEqual(p.view(13,1,len,now=100)[0],first)
        p.pause(now=101);p.view(13,1,len,now=101);self.assertEqual(p.page_number,1)

    def test_hidden_layout_does_not_consume_reading_time(self):
        p=ReadingPager();p.push(record('a','one two three four five six'));first=p.view(13,1,len,now=0)[0]
        p.suspend();self.assertEqual(p.view(13,1,len,now=100)[0],first)
        self.assertGreater(p.deadline,100)

    def test_latest_goes_to_latest_tail_and_unpauses(self):
        p=ReadingPager();p.push(record('a','old'));p.push(record('b','one two three four five six'))
        p.pause(now=0);p.latest()
        self.assertFalse(p.paused);self.assertEqual(p.view(13,1,len,now=10)[0],['› five six'])
        self.assertEqual(len(p.pending),1)

    def test_bounded_backlog_reports_skips_and_discard_recovers(self):
        p=ReadingPager(limit=3);p.push(record('a','active'));p.view(100,1,len,now=0)
        for i in range(10):p.push(record(str(i),'new '+str(i)))
        self.assertEqual(len(p.pending),3);self.assertEqual(p.skipped,8)
        self.assertIn('a',p.pending)
        p.discard('a');self.assertTrue(p.view(100,1,len,now=1)[0])

    def test_short_paragraph_history_has_no_duplicates(self):
        p=ReadingPager();p.push(record('a','one'));p.view(100,3,len,now=0)
        p.push(record('b','two'));p.view(100,3,len,now=4)
        p.push(record('c','three'));lines=p.view(100,3,len,now=8)[0]
        self.assertEqual(lines,['› one','› two','› three'])

    def test_reading_time_uses_words_and_chinese_characters(self):
        self.assertGreater(reading_seconds('word '*30),reading_seconds('word word'))
        self.assertGreater(reading_seconds('中文句子'*10),reading_seconds('中文'))
        self.assertGreater(reading_seconds('word '*8,1.5),reading_seconds('word '*8))

if __name__=='__main__':unittest.main()
