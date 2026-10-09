"""Installed screen-mode check using only a deliberately created test window."""
import threading
import time
import traceback
from unittest.mock import patch


def self_test():
    import tkinter as tk
    import native
    from engine import offline, Translator
    from screen_capture import capture_screen
    native.dpi_aware()
    offline()
    translator=Translator('en_zh')
    window=tk.Tk()
    window.title('随译 · 画面采集自检')
    window.geometry('850x220+50+50')
    window.configure(bg='white')
    window.attributes('-topmost',True)
    tk.Label(window,text='We should leave before the rain starts.\nBring an umbrella.',
             font=('Arial',-28),bg='white',fg='black',justify='left').pack(padx=30,pady=30,anchor='nw')
    window.update()
    hwnd=native.u.GetAncestor(window.winfo_id(),2)
    point=(window.winfo_rootx()+100,window.winfo_rooty()+50)
    result={'ok':False,'own_test_window_only':True,'no_audio_capture':True,'modes':{}}
    try:
        assert native.point_belongs_to_window(hwnd,point)
        for mode in ('auto','hover'):
            stopped=threading.Event()
            events=[];errors=[];start=time.monotonic()
            def emit(kind,data):
                events.append((kind,data))
                if kind=='caption':stopped.set()
            def run():
                try:
                    # Query a deterministic point in our own window; the real
                    # cursor is neither moved nor used to capture another app.
                    with patch('native.cursor_position',return_value=point):
                        capture_screen(dict(hwnd=hwnd,screen_mode=mode,language='en',speech_profile='general'),
                                       stopped,emit,translator)
                except BaseException:
                    errors.append(traceback.format_exc());stopped.set()
            thread=threading.Thread(target=run,daemon=True);thread.start()
            while not stopped.is_set() and time.monotonic()-start<45:
                window.update();time.sleep(.025)
            stopped.set();thread.join(8)
            assert not thread.is_alive(),'Screen worker did not stop'
            captions=[payload for kind,payload in events if kind=='caption']
            assert captions,(mode,errors,events)
            first=captions[0]
            assert 'leave before the rain starts' in first['source'],first
            assert '雨' in first['text'],first
            elapsed=time.monotonic()-start
            if mode=='hover':assert elapsed>=1.5
            result['modes'][mode]={'source':first['source'],'translation':first['text'],
                                   'elapsed_seconds':round(elapsed,3),'manual_roi_required':False}
        result['ok']=True
        return result
    finally:
        window.destroy()
