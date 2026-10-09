"""Render synthetic UI examples. Capture only this tool's own HWND, never the desktop."""
from pathlib import Path
import ctypes
import sys
import tkinter as tk
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


class PreviewApp(app.App):
    def _load(self):pass
    def save(self):pass
    def refresh_windows(self):pass
    def setup_tray(self):pass
    def list_audio(self):pass
    def poll(self):pass


class Hotkeys:
    def __init__(self,*args):pass
    def close(self):pass


def main():
    app.native.dpi_aware()
    app.native.Hotkeys=Hotkeys
    root=tk.Tk()
    panel=PreviewApp(root)
    try:
        root.title('随译 · 学习工作台 · 界面示例')
        root.geometry('1400x900+30+30')
        panel.status.set('界面示例 · 尚未采集 · 以下文字仅用于演示布局')
        panel.window_combo.configure(values=['示例窗口']);panel.window_combo.current(0)
        panel.mode.set('画面英文 → 中文翻译')
        panel.screen_mode.set('hover');panel.screen_method.set(app.SCREEN_METHODS['hover'])
        panel.update_screen_controls()
        panel.history.configure(state='normal')
        panel.history.insert('1.0',
            '01  We should leave before the rain starts.\n我们应该在下雨前出发。\n\n'
            '02  There is still time to listen once more.\n还有时间再听一遍。\n\n'
            '03  A short pause can make a long sentence easier to follow.\n稍作停顿，长句也会更容易理解。\n')
        panel.history.configure(state='disabled')
        panel.dictionary_panel.query.set('rain')
        panel.dictionary_panel.output.configure(state='normal')
        panel.dictionary_panel.output.delete('1.0','end')
        panel.dictionary_panel.output.insert('1.0','rain  /reɪn/\n\n雨；下雨\n\n示例释义，仅用于界面演示。\n实际查词使用离线 ECDICT。')
        panel.dictionary_panel.output.configure(state='disabled')
        panel.replay_status.set('采集语音后，可在这里选择最近片段并循环回听。')
        destination=ROOT/'docs/images';destination.mkdir(parents=True,exist_ok=True)
        for key,name in [('vertin','rain'),('ryuko','scarlet')]:
            panel.theme.set(key);panel.change_theme()
            root.update()
            ctypes.windll.user32.GetAncestor.restype=ctypes.c_void_p
            ctypes.windll.user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
            hwnd=ctypes.windll.user32.GetAncestor(root.winfo_id(),2)
            shot=ImageGrab.grab(window=int(hwnd))
            if shot.width<500 or shot.height<500:raise RuntimeError('Invalid own-window screenshot')
            shot.save(destination/f'workspace-{name}.png')
            print(f'Wrote workspace-{name}.png')
    finally:
        panel.quit()


if __name__=='__main__':main()
