import unittest
from core import *

class LayoutTests(unittest.TestCase):
    def test_edge_touch_is_not_overlap(self):
        self.assertFalse(overlaps([0,0,100,100],[0,100,100,140]))
        self.assertTrue(overlaps([0,0,100,100],[0,99,100,140]))

    def test_a_rejects_no_room(self):
        self.assertIsNone(caption_rect('A',[400,1050,1750,1170],None,[0,0,2008,1192],34))

    def test_user_screenshot_a_fits(self):
        r=caption_rect('A',[427,1060,1780,1145],None,[0,0,2008,1192],30)
        self.assertEqual(r,[427,1151,1780,1185])

    def test_move_resize_tracks_relative_region(self):
        relative=relative_rect([110,120,310,180],[10,20,410,220])
        self.assertEqual(absolute_rect(relative,[50,100,850,500]),[250,300,650,420])

    def test_wrap_preserves_information(self):
        for text in ['Never delete 12345678901234567890 without a backup.', '不要删除任何未备份的文件。']:
            lines=fit_lines(text,12,len)
            self.assertTrue(all(len(s)<=12 for s in lines))
            self.assertEqual(''.join(''.join(lines).split()),''.join(text.split()))

if __name__=='__main__':
    unittest.main()
