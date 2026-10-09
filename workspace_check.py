"""Packaged UI/resource smoke check; no capture, preferences, tray or hotkeys."""
import time
import tkinter as tk
from runtime_paths import BUNDLE_ROOT


def self_test():
    import app
    from audio_review import ReviewClip, encode_wav
    class SilentApp(app.App):
        def _load(self):pass
        def save(self):pass
        def refresh_windows(self):pass
        def setup_tray(self):pass
        def list_audio(self):pass
    class Hotkeys:
        def __init__(self,*args):pass
        def close(self):pass
    previous=app.native.Hotkeys
    app.native.Hotkeys=Hotkeys
    root=tk.Tk();root.withdraw();errors=[]
    root.report_callback_exception=lambda *args:errors.append(str(args))
    panel=None
    try:
        panel=SilentApp(root)
        for key in ('vertin','ryuko'):
            panel.theme.set(key);panel.change_theme()
            from workspace_ui import PALETTES
            assert panel.workspace.palette==PALETTES[key]
            assert not panel.workspace.images
        has_dictionary=(BUNDLE_ROOT/'dictionary/ecdict.sqlite3').is_file()
        if has_dictionary:
            panel.dictionary_panel.show_query('rain')
            deadline=time.monotonic()+5
            while panel.dictionary_panel.busy and time.monotonic()<deadline:
                root.update();time.sleep(.02)
            assert '雨' in panel.dictionary_panel.output.get('1.0','end')
        clip=ReviewClip('check',b'\0\0'*1600)
        panel.clips.add(clip);panel.refresh_clips()
        assert panel.clip_ids==['check']
        assert encode_wav(clip).startswith(b'RIFF')
        assert not errors,errors
        return dict(ok=True,themes=2,character_art=False,offline_dictionary=has_dictionary,
                    dictionary_skipped=not has_dictionary,audio_resources=True,no_capture=True)
    finally:
        if panel:panel.quit()
        else:root.destroy()
        app.native.Hotkeys=previous
