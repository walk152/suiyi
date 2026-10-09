import unittest
from unittest.mock import patch
from types import SimpleNamespace
from screen_capture import HoverTracker, hover_crop, actual_region, image_changed
from translation_text import token_batches


class ScreenCaptureTests(unittest.TestCase):
    def test_dwell_and_movement_reset(self):
        t=HoverTracker()
        self.assertFalse(t.update((100,100),0))
        self.assertFalse(t.update((104,100),1.49))
        self.assertTrue(t.update((102,99),1.5))
        self.assertFalse(t.update((120,100),1.6))
        self.assertTrue(t.update((120,100),3.1))
        self.assertFalse(t.update((120,100),4,False))
        self.assertFalse(t.update((120,100),5))

    def test_hover_crop_fits_negative_monitor(self):
        self.assertEqual(hover_crop([-1920,0,0,1080],(-1800,100)),[-1920,0,-120,600])
        self.assertEqual(hover_crop([10,20,310,220],(20,40)),[10,20,310,220])

    def test_auto_window_requires_no_roi(self):
        with patch('native.window_rect',return_value=[-50,-30,500,400]), patch('native.client_rect',return_value=[0,0,500,400]):
            self.assertEqual(actual_region({'hwnd':123,'screen_mode':'auto'}),[0,0,500,400])
            self.assertIsNone(actual_region({'hwnd':123,'screen_mode':'region'}))
            cfg={'hwnd':123,'screen_mode':'region','roi_relative':[0,0,1,1]}
            self.assertEqual(actual_region(cfg),[0,0,500,400])

    def test_static_frame_and_small_text_change(self):
        import numpy as np
        blank=np.zeros((270,480),dtype='uint8')
        self.assertFalse(image_changed(blank,blank.copy()))
        changed=blank.copy();changed[30:35,10:45]=200
        self.assertTrue(image_changed(blank,changed))

    def test_long_input_not_lost_at_request_limit(self):
        tokenizer=SimpleNamespace(encode=lambda text,**kw:text.split())
        text=' '.join('word'+str(i) for i in range(700))
        result=token_batches(text,tokenizer)
        self.assertEqual([token for group in result for token in group],text.split())
        self.assertTrue(all(0<len(group)<=128 for group in result))

    def test_names_not_split_on_title(self):
        tokenizer=SimpleNamespace(encode=lambda text,**kw:text.split())
        self.assertEqual(token_batches('Dr. Smith is here. Bring a coat.',tokenizer),
                         [['Dr.','Smith','is','here.'],['Bring','a','coat.']])


if __name__=='__main__':unittest.main()
