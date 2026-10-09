import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
from app import App
from core import relative_rect

class Value:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


class ScreenUITests(unittest.TestCase):
    def test_auto_starts_without_manual_roi_or_overlay(self):
        a=SimpleNamespace(installing_model=False,process=None,hwnd=123,roi_relative=None,
            mode=Value('画面英文 → 中文翻译'),screen_mode=Value('auto'),get_layout=lambda:(None,'wait'),
            pause_gap=Value('1.2 秒'),speech_device=Value('仅CPU'),speech_model=Value('英语增强 small.en'),
            speech_hint=Value(''),speech_profile=Value('通用'),speech_review=Value(True),idle_release=Value(True),
            clips=Mock(),refresh_clips=Mock(),start_button=Mock(),status=Value(''),save=Mock())
        with patch('app.native.window_rect',return_value=[0,0,900,600]),patch('app.mp.Event'),patch('app.mp.Queue'),patch('app.mp.Process') as process:
            App.toggle_running(a)
        process.return_value.start.assert_called_once()
        cfg=process.call_args.kwargs['args'][0]
        self.assertEqual(cfg['screen_mode'],'auto')
        self.assertIsNone(cfg['roi_relative'])

    def test_anchor_coordinates_follow_original_capture_window(self):
        a=SimpleNamespace(hwnd=123,overlay=Mock())
        window=[-100,30,900,630];source=[20,80,500,110]
        App.set_screen_anchor(a,dict(source_rect=source,capture_window_rect=window,blocked_rects=[source]))
        self.assertEqual(a.ocr_anchor_relative,relative_rect(source,window))
        self.assertTrue(a.ocr_overlay_safe)
        App.set_screen_anchor(a,None)
        self.assertIsNone(a.ocr_anchor_relative)
        a.overlay.hide.assert_called_once()


if __name__=='__main__':unittest.main()
