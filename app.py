"""Suiyi desktop prototype: screen/audio only. No game files or injection."""
from pathlib import Path
import multiprocessing as mp
import queue, threading, json, time, sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
import native
from runtime_paths import APP_ROOT, settings_path, write_settings
from model_pack import turbo_ready, install_pack
from core import overlaps, valid_rect, relative_rect, absolute_rect, fit_lines, caption_rect
from captions import CaptionHistory, visible_lines
from learning import PROFILES
from reading import ReadingPager

ROOT = APP_ROOT
MODES = {
    '英文声音 → 英文原文字幕': ('audio', None, 'en'),
    '英文声音 → 中文字幕': ('audio', 'en_zh', 'en'),
    '中文声音 → 英文字幕': ('audio', 'zh_en', 'zh'),
    '画面英文 → 中文翻译': ('screen', 'en_zh', 'en'),
    '画面中文 → 英文翻译': ('screen', 'zh_en', 'zh'),
}
SPEECH_MODELS={'英语增强 small.en':'small.en','大模型 turbo':'turbo','低占用 base':'base'}
SCREEN_METHODS = {
    'auto': '自动识别所选窗口',
    'hover': '鼠标停留 1.5 秒 · 翻译附近句子',
    'region': '手动框选固定区域',
}

class RectPicker:
    def __init__(self, root, title, callback):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', .35)
        self.d = native.desktop()
        x, y, r, b = self.d
        self.win.geometry(f'{r-x}x{b-y}{x:+d}{y:+d}')
        self.canvas = tk.Canvas(self.win, bg='black', highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.create_text((r-x)//2, 50, text=title+'  ·  拖动框选，Esc 取消', fill='white', font=('Microsoft YaHei UI', 22))
        self.start = None
        self.box = None
        self.callback = callback
        self.canvas.bind('<ButtonPress-1>', self.begin)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.end)
        self.win.bind('<Escape>', lambda e: self.finish(None))
        self.win.focus_force()

    def begin(self, e):
        self.start = (e.x_root, e.y_root)
        if self.box:
            self.canvas.delete(self.box)
        self.box = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline='#b1ffad', width=3)

    def move(self, e):
        if self.start:
            self.canvas.coords(self.box, self.start[0]-self.d[0], self.start[1]-self.d[1], e.x, e.y)

    def end(self, e):
        if not self.start:
            return
        x, y = self.start
        rect = [min(x, e.x_root), min(y, e.y_root), max(x, e.x_root), max(y, e.y_root)]
        self.finish(rect if valid_rect(rect) else None)

    def finish(self, rect):
        self.win.destroy()
        self.callback(rect)

class Overlay:
    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.configure(bg='#010203')
        self.win.attributes('-transparentcolor', '#010203')
        self.canvas = tk.Canvas(self.win, bg='#010203', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.font = tkfont.Font(family='Microsoft YaHei UI', size=-28)
        self.excluded = False

    def hide(self):
        self.win.withdraw()

    def draw(self, rect, lines, mode, size, colors=None):
        x, y, r, b = rect
        self.font.configure(size=-size)
        self.win.geometry(f'{r-x}x{b-y}{x:+d}{y:+d}')
        bg = '#010203' if mode == 'A' else '#101c16'
        self.canvas.configure(bg=bg)
        self.canvas.delete('all')
        line_height = self.font.metrics('linespace')
        total = len(lines)*line_height
        top = max(3, ((b-y)-total)//2)
        for i, text in enumerate(lines):
            tx = 8 if mode == 'A' else (r-x)//2
            anchor = 'nw' if mode == 'A' else 'n'
            ty = top+i*line_height
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                self.canvas.create_text(tx+dx, ty+dy, text=text, font=self.font, fill='#090c0a', anchor=anchor)
            self.canvas.create_text(tx, ty, text=text, font=self.font, fill=colors[i] if colors else '#eef6e6', anchor=anchor)
        self.win.deiconify()
        self.win.update_idletasks()
        self.excluded = native.style_overlay(self.win)

class App:
    screen_methods = SCREEN_METHODS

    def __init__(self, root):
        self.root = root
        root.title('随译 · v0.5 公开版（学习工作台）')
        root.geometry(f'{min(1420, root.winfo_screenwidth()-80)}x{min(940, root.winfo_screenheight()-100)}')
        root.minsize(1100, 720)
        root.configure(bg='#f3f6f1')
        self.ui_events = queue.Queue()
        self.events = mp.Queue(maxsize=20)
        self.process = None
        self.controls=None
        self.dictionary=None
        from audio_review import ClipStore, PlaybackController
        self.clips=ClipStore()
        self.playback=PlaybackController()
        self.clip_ids=[]
        self.replay_request=0
        self.replay_pending=None
        self.replay_token=None
        self.replay_held=False
        self.replay_deadline=0
        self.audio_loop=tk.BooleanVar(value=False)
        self.replay_status=tk.StringVar(value='识别语音后可回听最近片段。仅缓存约 60 秒，不写入录音文件。')
        self.theme=tk.StringVar(value='vertin')
        self.history_dragging=False
        self.render_inputs=None
        self.stopped = None
        self.tray = None
        self.closing = False
        self.hwnd = 0
        self.roi_relative = None
        self.ocr_anchor_relative = None
        self.ocr_blocked_relative = []
        self.ocr_overlay_safe = True
        self.dock = None
        self.hidden = False
        self.caption = ''
        self.captions = CaptionHistory(limit=40)
        self.reader = ReadingPager(limit=40)
        self.page = 0
        self.next_page = 0
        self.expiry = 0
        self.last_render = None
        self.layout = tk.StringVar(value='A')
        self.mode = tk.StringVar(value=next(iter(MODES)))
        self.screen_mode = tk.StringVar(value='auto')
        self.screen_method = tk.StringVar(value=SCREEN_METHODS['auto'])
        self.screen_hint = tk.StringVar(value='画面翻译默认自动识别所选窗口，无需框选。')
        self.size = tk.IntVar(value=28)
        self.keep_count = tk.IntVar(value=3)
        self.max_lines = tk.IntVar(value=6)
        self.reading_protect=tk.BooleanVar(value=True)
        self.reading_pace=tk.StringVar(value='正常阅读')
        self.pause_gap=tk.StringVar(value='1.2 秒（自然停顿）')
        self.speech_device = tk.StringVar(value='GPU优先')
        self.speech_model = tk.StringVar(value='英语增强 small.en')
        self.speech_hint = tk.StringVar(value='')
        self.speech_profile = tk.StringVar(value='重返未来：1999')
        self.speech_review=tk.BooleanVar(value=True)
        self.idle_release=tk.BooleanVar(value=True)
        self.installing_model=False
        self.turbo_status=tk.StringVar(value='turbo 已安装' if turbo_ready() else 'turbo 未安装 · 可选扩展，默认英语模型可直接使用')
        self.visible_status = tk.StringVar(value='最近 3 段，最多 6 行；蓝色为可修订草稿。')
        self.status = tk.StringVar(value='选择目标窗口和翻译内容，再点击开始。画面模式默认自动识别，无需框选。')
        self.region_label = tk.StringVar(value='尚未框选原字幕区')
        self.dock_label = tk.StringVar(value='B 区域未设置：请在目标窗口外留出空间')
        self._load()
        if self.dock:
            self.dock_label.set(f'B：{self.dock[2]-self.dock[0]} × {self.dock[3]-self.dock[1]} 像素，已保存')
        self.overlay = Overlay(root)
        self._build()
        self.refresh_windows()
        self.hotkeys = native.Hotkeys(lambda k, v: self.ui_events.put((k, v)))
        threading.Thread(target=self.setup_tray, daemon=True).start()
        threading.Thread(target=self.list_audio, daemon=True).start()
        root.protocol('WM_DELETE_WINDOW', self.minimize)
        root.after(100, self.poll)

    def _load(self):
        try:
            data = json.loads(settings_path().read_text(encoding='utf-8'))
            self.layout.set(data.get('layout', 'A') if data.get('layout') in ['A','B'] else 'A')
            if data.get('mode') in MODES:
                self.mode.set(data['mode'])
            screen_mode = data.get('screen_mode', 'auto')
            self.screen_mode.set(screen_mode if screen_mode in SCREEN_METHODS else 'auto')
            self.screen_method.set(SCREEN_METHODS[self.screen_mode.get()])
            self.size.set(max(18, min(40, int(data.get('size', 28)))))
            self.dock = data.get('dock') if valid_rect(data.get('dock')) else None
            self.keep_count.set(max(1,min(8,int(data.get('keep_count',3)))))
            self.max_lines.set(max(1,min(12,int(data.get('max_lines',6)))))
            self.reading_protect.set(bool(data.get('reading_protect',True)))
            self.reading_pace.set('慢速阅读' if data.get('reading_pace')=='slow' else '正常阅读')
            self.pause_gap.set({.6:'0.6 秒（较快断句）',1.2:'1.2 秒（自然停顿）',1.8:'1.8 秒（长停顿）'}.get(data.get('speech_pause',1.2),'1.2 秒（自然停顿）'))
            self.speech_device.set('仅CPU' if data.get('speech_device')=='cpu' else 'GPU优先')
            self.speech_model.set(next((label for label,value in SPEECH_MODELS.items()
                                       if value==data.get('speech_model','small.en')),'英语增强 small.en'))
            self.speech_hint.set(str(data.get('speech_hint',''))[:500])
            self.speech_profile.set(next((k for k,v in PROFILES.items() if v==data.get('speech_profile','1999')),'通用'))
            self.speech_review.set(bool(data.get('speech_review',True)))
            self.idle_release.set(bool(data.get('idle_release',True)))
            self.theme.set(data.get('theme','vertin') if data.get('theme') in ('vertin','ryuko') else 'vertin')
        except (OSError, ValueError, TypeError):
            pass

    def save(self):
        data = dict(theme=self.theme.get(), layout=self.layout.get(), mode=self.mode.get(), screen_mode=self.screen_mode.get(), size=self.size.get(), dock=self.dock,
                    keep_count=self.keep_count.get(),max_lines=self.max_lines.get(),
                    reading_protect=self.reading_protect.get(),reading_pace='slow' if self.reading_pace.get()=='慢速阅读' else 'normal',
                    speech_pause=float(self.pause_gap.get().split()[0]),
                    speech_device='cpu' if self.speech_device.get()=='仅CPU' else 'cuda',
                    speech_model=SPEECH_MODELS[self.speech_model.get()],
                    speech_hint=self.speech_hint.get()[:500],speech_profile=PROFILES[self.speech_profile.get()],speech_review=self.speech_review.get(),idle_release=self.idle_release.get())
        write_settings(data)

    def _build(self):
        from workspace_ui import Workspace
        self.workspace = Workspace(self, MODES, SPEECH_MODELS, PROFILES)

    def change_theme(self):
        self.workspace.apply_theme()
        self.save()

    def refresh_windows(self):
        previous = self.hwnd
        self.window_items = native.windows()
        self.window_combo['values'] = [title for _, title in self.window_items]
        if self.window_items:
            index = next((i for i,(h,_) in enumerate(self.window_items) if h == previous),
                         next((i for i,(_,t) in enumerate(self.window_items) if 'MuMu' in t or '重返未来' in t),0))
            self.window_combo.current(index)
            if self.window_items[index][0] != previous:
                self.select_window()

    def select_window(self, event=None):
        index = self.window_combo.current()
        if index < 0:
            return
        self.stop()
        self.hwnd = self.window_items[index][0]
        self.roi_relative = None
        self.region_label.set('手动区域未设置；自动识别与鼠标停留无需框选')
        self.update_screen_controls()

    def list_audio(self):
        try:
            import soundcard as sc
            speakers = [(s.id,s.name) for s in sc.all_speakers()]
            default = sc.default_speaker()
            self.ui_events.put(('devices', (speakers, default.id if default else '')))
        except Exception as exc:
            self.ui_events.put(('warning', f'音频设备不可用：{exc}；仍可使用画面模式。'))

    def input_changed(self):
        self.stop()
        self.update_screen_controls()
        self.save()
        is_audio = MODES[self.mode.get()][0] == 'audio'
        self.status.set('turbo 尚未安装。请点“安装 turbo 扩展…”选择离线扩展包，或切回 small.en。'
                        if is_audio and SPEECH_MODELS[self.speech_model.get()]=='turbo' and not turbo_ready()
                        else ('模式已更改，点击开始采集。' if is_audio else self.screen_hint.get()+' 点击开始采集。'))

    def update_screen_controls(self):
        is_screen = MODES[self.mode.get()][0] == 'screen'
        messages = {
            'auto': '自动检测所选窗口的文字；画面不变时降低检查频率，无需框选。',
            'hover': '将鼠标停在目标窗口文字附近 1.5 秒，即可翻译附近句子。',
            'region': '只识别手动框选的固定区域；请先点“框选区域”。',
        }
        self.screen_hint.set(messages[self.screen_mode.get()] if is_screen else '画面识别方式仅用于画面翻译；声音模式按所选音频设备采集。')
        if hasattr(self, 'screen_mode_combo'):
            self.screen_mode_combo.configure(state='readonly' if is_screen else 'disabled')
            self.screen_pick_button.configure(state='normal' if is_screen else 'disabled')

    def screen_method_changed(self):
        was_running = self.process is not None and MODES[self.mode.get()][0] == 'screen'
        self.screen_mode.set(next((key for key, label in SCREEN_METHODS.items()
                                   if label == self.screen_method.get()), 'auto'))
        self.input_changed()
        if was_running:
            self.toggle_running()

    def install_turbo(self):
        if self.installing_model:return
        if turbo_ready():
            self.turbo_status.set('turbo 已安装，可从模型列表切换使用。');return
        package=filedialog.askopenfilename(parent=self.root,title='选择 turbo 离线扩展包',filetypes=[('随译模型扩展','*.suiyimodel')])
        if not package:return
        self.stop();self.installing_model=True
        self.install_model_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.turbo_status.set('正在校验并安装 turbo…')
        def run_import():
            last=-1
            def progress(value):
                nonlocal last
                if value!=last:self.ui_events.put(('model_progress',value));last=value
            try:
                install_pack(package,progress)
                self.ui_events.put(('model_installed',''))
            except Exception as exc:self.ui_events.put(('model_installed',str(exc)))
        threading.Thread(target=run_import,daemon=True).start()

    def source_rect(self):
        window = native.window_rect(self.hwnd)
        if MODES[self.mode.get()][0] == 'screen' and self.screen_mode.get() != 'region':
            return absolute_rect(self.ocr_anchor_relative, window) if window and self.ocr_anchor_relative else None
        return absolute_rect(self.roi_relative, window) if window and self.roi_relative else None

    def pick(self, what):
        if not native.window_rect(self.hwnd):
            messagebox.showinfo('随译', '请先选择一个可见目标窗口。')
            return
        self.stop()
        self.overlay.hide()
        self.root.withdraw()
        def selected(rect):
            self.root.deiconify()
            if rect:
                window = native.window_rect(self.hwnd)
                if not window:
                    self.status.set('目标窗口已关闭，请重新选择。'); return
                if what == 'roi':
                    rect = [max(rect[0],window[0]),max(rect[1],window[1]),min(rect[2],window[2]),min(rect[3],window[3])]
                    if not valid_rect(rect):
                        self.status.set('选区必须位于目标窗口内。'); return
                    self.roi_relative = relative_rect(rect, window)
                    self.region_label.set(f'{rect[2]-rect[0]} × {rect[3]-rect[1]} 像素')
                    if MODES[self.mode.get()][0] == 'screen':
                        self.screen_mode.set('region')
                        self.screen_method.set(SCREEN_METHODS['region'])
                        self.update_screen_controls()
                    self.status.set('原字幕区域已设置。A 将显示在其下方，OCR 只读取此区域。')
                else:
                    if overlaps(rect, window):
                        self.status.set('B 区域与目标窗口重叠，未保存。请手动缩小游戏，或选第二屏。'); return
                    if rect[2]-rect[0] < 200 or rect[3]-rect[1] < 50:
                        self.status.set('B 区域太小，请至少选择 200 × 50 像素。'); return
                    self.dock = rect
                    self.dock_label.set(f'B：{rect[2]-rect[0]} × {rect[3]-rect[1]} 像素，已设置')
                    self.status.set('B 字幕区域已设置；不会修改或移动游戏窗口。')
                self.save()
        self.root.after(250, lambda: RectPicker(self.root, '框选全部原字幕文字' if what=='roi' else '框选目标窗口外的空闲区域', selected))

    def get_layout(self):
        source = self.source_rect()
        wr = native.window_rect(self.hwnd)
        if not wr:
            return None, '目标窗口不可见；字幕已隐藏。'
        mode = self.layout.get()
        if mode == 'A' and not source:
            if MODES[self.mode.get()][0] == 'screen' and self.screen_mode.get() != 'region':
                return None, '等待检测到文字；译文会保留在实时文本区。'
            return None, '请先框选原字幕区域，或切换 B 独立字幕条。'
        if mode == 'B' and (not valid_rect(self.dock) or overlaps(self.dock, wr)):
            return None, 'B 区域未设置或与目标窗口重叠；请选择窗口外空闲区域。'
        self.overlay.font.configure(size=-self.size.get())
        bounds = native.desktop()
        if mode == 'A' and MODES[self.mode.get()][0] == 'screen' and source:
            source = list(source)
            source[2] = min(bounds[2], max(source[2], source[0]+320))
        rect = caption_rect(mode, source, self.dock, bounds, self.overlay.font.metrics('linespace'),self.max_lines.get())
        if rect is None:
            return None, 'A 下方空间不足，请切换 B 或重新设置原字幕区域。'
        if mode == 'A' and MODES[self.mode.get()][0] == 'screen':
            blocked = [absolute_rect(item, wr) for item in self.ocr_blocked_relative]
            if not self.ocr_overlay_safe or any(overlaps(rect, item) for item in blocked):
                return None, '原文下方没有安全空位，译文已保留在实时文本区；可切换 B 字幕条。'
        return rect, ''

    def switch_layout(self):
        self.last_render = None
        self.reader.suspend()
        self.page = 0
        self.next_page = 0
        self.save()
        rect, reason = self.get_layout()
        self.status.set(reason or f'已切换 {self.layout.get()}，采集任务无需重启。')
        if not rect:
            self.overlay.hide()

    def resize(self):
        self.last_render = None
        self.page = 0
        self.next_page = 0
        if hasattr(self,'reader'):
            self.reader.suspend();self.reader.wrap_key=None
        if hasattr(self,'speech_model'):
            self.save()

    def demo(self):
        for index,text in enumerate(['We should leave before the rain starts.',
                                    'I thought you said the station was just round the corner.',
                                    'It is. We can still make it if we hurry.']):
            self.show_caption({'source':'位置测试，非实时识别','text':text,'cost':0,'kind':'演示',
                               'id':f'demo-{index}','final':index<2,'revision':1})

    def toggle_running(self):
        if self.installing_model:
            self.status.set('正在安装 turbo，请等待完成。');return
        if self.process is not None:
            self.stop(); self.status.set('已停止采集，识别与翻译模型已释放。'); return
        if not self.hwnd or not native.window_rect(self.hwnd):
            self.status.set('请先选择可见的目标窗口。'); return
        source, direction, language = MODES[self.mode.get()]
        if source=='audio' and SPEECH_MODELS[self.speech_model.get()]=='turbo' and not turbo_ready():
            self.status.set('turbo 是选装模型，请先安装离线扩展包，或选择 small.en / base。');return
        if source == 'screen' and self.screen_mode.get() == 'region' and not self.roi_relative:
            self.status.set('画面翻译需要先框选原字幕 / OCR 区域。'); return
        rect, reason = self.get_layout()
        if not rect and source != 'screen':
            self.status.set(reason); return
        cfg = dict(input=source, direction=direction, language=language, hwnd=self.hwnd, roi_relative=self.roi_relative,
                   screen_mode=self.screen_mode.get(),
                   audio_review=True,
                   speech_pause=float(self.pause_gap.get().split()[0]),
                   speech_device='cpu' if self.speech_device.get()=='仅CPU' else 'cuda',
                   speech_model=SPEECH_MODELS[self.speech_model.get()],
                   speech_hint=self.speech_hint.get()[:500],speech_profile=PROFILES[self.speech_profile.get()],speech_review=self.speech_review.get(),
                   idle_release_seconds=180 if self.idle_release.get() else 0)
        if source == 'audio':
            index = self.audio_combo.current()
            if not getattr(self,'speakers',None) or index < 0:
                self.status.set('未找到输出设备，请使用画面模式。'); return
            cfg['speaker_id'] = self.speakers[index][0]
        from engine import run
        self.clips.clear();self.refresh_clips()
        self.stopped = mp.Event()
        self.events = mp.Queue(maxsize=20)
        self.controls=mp.Queue(maxsize=4)
        self.process = mp.Process(target=run, args=(cfg,self.stopped,self.events,self.controls), daemon=True)
        self.process.start()
        self.start_button.configure(text='停止采集 / 释放模型')
        self.status.set('正在启动本地模型…')
        self.save()

    def stop(self):
        self.stop_audio()
        if self.process:
            self.stopped.set()
            self.process.join(timeout=.25)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
            self.process.close()
            self.process = None
            # A terminated worker may leave a partial queue write. Never poll that pipe again.
            old=self.events;self.events=mp.Queue(maxsize=20)
            old.cancel_join_thread();old.close()
        if self.controls is not None:
            self.controls.cancel_join_thread();self.controls.close();self.controls=None
        self.caption = ''
        self.ocr_anchor_relative = None
        self.ocr_blocked_relative = []
        self.ocr_overlay_safe = True
        self.captions.clear()
        self.reader.reset()
        if hasattr(self,'read_pause_button'):self.read_pause_button.configure(text='暂停翻页')
        self.overlay.hide()
        self.last_render = None
        if hasattr(self,'history'):
            self.history_dragging=False;self.history.tag_remove('sel','1.0','end')
            self.refresh_history()
        if hasattr(self,'start_button'):
            self.start_button.configure(text='开始采集')

    def show_caption(self, data):
        if data.get('screen_mode'):
            self.set_screen_anchor(data)
            # Hovering is an explicit request for this sentence. Keep older
            # entries in history without paging them under the new sentence.
            if data['screen_mode'] == 'hover':
                self.reader.reset()
        if self.clips.from_caption(data):self.refresh_clips()
        # Text history/paging must not retain audio that aged out of the 60 s store.
        if 'audio_clip' in data:data={k:v for k,v in data.items() if k!='audio_clip'}
        if not self.captions.update(data):
            return
        self.caption = data['text']
        ident=data.get('id',next(reversed(self.captions.records)))
        self.reader.push(self.captions.records[ident])
        self.page = 0
        self.next_page = 0
        self.expiry = time.monotonic()+max(10, len(self.caption)*.16)
        self.last_render = None
        self.refresh_history()
        stage='定稿' if data.get('final',True) else '草稿（后续会修订）'
        if data.get('uncertain'):stage+=' · 存疑，请结合原声'
        if data.get('retried'):stage+=' · 已复核一次'
        if data.get('learned'):stage+=' · 已用纠错记忆'
        if data.get('review_skipped'):stage+=' · 为跟上语音跳过复核'
        lag=f" · 片段尾后 {data['lag']:.2f} 秒" if 'lag' in data else ''
        self.status.set(f"{data['kind']} · {stage} · 处理 {data['cost']:.2f} 秒{lag}")

    def set_screen_anchor(self, data):
        self.ocr_anchor_relative = None
        self.ocr_blocked_relative = []
        self.ocr_overlay_safe = False
        if data:
            window = data.get('capture_window_rect') or native.window_rect(self.hwnd)
            source = data.get('source_rect')
            if window and source and window[2] > window[0] and window[3] > window[1]:
                self.ocr_anchor_relative = relative_rect(source, window)
                self.ocr_blocked_relative = [relative_rect(box, window) for box in data.get('blocked_rects', [])]
                self.ocr_overlay_safe = data.get('overlay_safe', True)
        self.last_render = None
        if not data:
            self.overlay.hide()

    def refresh_history(self):
        if self.history_dragging or self.history.tag_ranges('sel'):return
        scroll_position=self.history.yview()
        follow=scroll_position[1]>.97
        self.history.configure(state='normal')
        self.history.delete('1.0','end')
        for item in self.captions.records.values():
            marker='?' if item.get('uncertain') else ('✓' if item['final'] else '…')
            text=item['text'] if item['source']==item['text'] else item['source']+'\n'+item['text']
            if item.get('learned'):text+='\n[记忆纠错；原识别：'+item.get('raw_source','')+']'
            self.history.insert('end',f'{marker} {text}\n\n')
        if follow:self.history.see('end')
        else:self.history.yview_moveto(scroll_position[0])
        self.history.configure(state='disabled')

    def apply_names(self):
        # Keep heavy audio/numpy imports out of the UI process.
        value=self.speech_hint.get().strip()[:500];self.speech_hint.set(value);self.save()
        if self.process is not None and self.controls is not None:
            try:self.controls.put_nowait({'speech_hint':value,'speech_profile':PROFILES[self.speech_profile.get()],'reload_memory':True})
            except queue.Full:
                self.status.set('专名更新队列忙，请稍后再点“应用专名”。');return
        self.status.set('专名已保存；正在采集时会在下一段生效。提示只辅助辨音，不强行替换相近单词。')

    def open_learning(self, recent=False):
        from learning_ui import LearningWindow
        source=''
        if recent and self.captions.records:
            item=next(reversed(self.captions.records.values()))
            source=item.get('raw_source',item['source'])
        LearningWindow(self.root,PROFILES[self.speech_profile.get()],MODES[self.mode.get()][2],self.apply_names,source)

    def quality_preset(self):
        self.stop();self.speech_device.set('GPU优先');self.speech_profile.set('重返未来：1999');self.speech_review.set(True)
        self.idle_release.set(False)
        self.speech_model.set('大模型 turbo' if turbo_ready() else '英语增强 small.en')
        self.save();self.status.set('已选择 '+self.speech_model.get()+' / GPU / 1999 词库；静音保留模型、不转写，优先快速恢复。点击开始采集。'
            +('' if turbo_ready() else ' turbo 尚未安装，本次不下载任何模型。'))

    def add_name(self, name):
        name=' '.join(name.strip().split())[:60]
        if not name:return
        names=[n.strip() for n in self.speech_hint.get().replace('，',',').split(',') if n.strip()]
        if name.casefold() not in [n.casefold() for n in names]:names.append(name)
        self.speech_hint.set(', '.join(names)[:500]);self.apply_names()

    def open_dictionary(self,query='',context=''):
        from dictionary_ui import DictionaryWindow
        if self.dictionary is None or self.dictionary.closed:
            self.dictionary=DictionaryWindow(self.root,self.add_name,palette=self.workspace.palette)
        self.dictionary_panel.show_query(query,context)
        self.dictionary.show(query,context)
        return 'break'

    def lookup_clicked(self,event):
        from lexicon import word_at
        widget=event.widget
        index=widget.index(f'@{event.x},{event.y}')
        line,column=map(int,index.split('.'))
        text=widget.get(f'{line}.0',f'{line}.end')
        self.history_dragging=False
        word=word_at(text,column)
        if word:return self.open_dictionary(word,text)

    def lookup_selected(self):
        try:
            query=self.history.get('sel.first','sel.last')
            context=self.history.get('sel.first linestart','sel.last lineend')
        except tk.TclError:query='';context=''
        return self.open_dictionary(query,context)

    def refresh_clips(self):
        old=self.clip_ids[self.clip_combo.current()] if 0<=self.clip_combo.current()<len(self.clip_ids) else None
        follow=not self.clip_ids or old==self.clip_ids[-1]
        clips=self.clips.list()
        self.clip_ids=[c.ident for c in clips]
        self.clip_combo['values']=[f'{i+1:02d} · {c.seconds:.1f}s · {c.source[:62]}' for i,c in enumerate(clips)]
        if self.clip_ids:
            self.clip_combo.current(len(self.clip_ids)-1 if follow or old not in self.clip_ids else self.clip_ids.index(old))
        else:self.clip_combo.set('')

    def play_audio(self):
        index=self.clip_combo.current()
        if not 0<=index<len(self.clip_ids):
            self.replay_status.set('还没有可回听片段。请先使用声音模式完成一段识别。');return
        clip=self.clips.get(self.clip_ids[index])
        if clip is None:self.refresh_clips();return
        self.stop_audio()
        self.replay_request+=1
        self.replay_pending=(self.replay_request,clip,self.audio_loop.get())
        if self.process is not None and self.process.is_alive() and MODES[self.mode.get()][0]=='audio':
            if self.controls is None:self.replay_pending=None;return
            try:self.controls.put_nowait({'replay_hold':True,'request_id':self.replay_request})
            except queue.Full:
                self.replay_pending=None;self.replay_status.set('控制队列忙，请稍后再播放。');return
            self.replay_held=True;self.replay_deadline=time.monotonic()+15
            self.replay_status.set('正在暂停识别，随后开始回听…')
        else:self.begin_replay(self.replay_request)

    def begin_replay(self,request_id):
        if not self.replay_pending or self.replay_pending[0]!=request_id:return
        _,clip,loop=self.replay_pending;self.replay_pending=None
        try:
            self.replay_token=self.playback.start(clip,loop=loop)
            self.replay_status.set(('循环回听中' if loop else '回听中')+' · 识别暂缓；请暂停游戏对白，结束后自动恢复。')
        except Exception as exc:
            self.stop_audio();self.replay_status.set('无法播放：'+str(exc))

    def release_replay(self):
        if self.replay_held and self.controls is not None:
            try:self.controls.put_nowait({'replay_hold':False,'request_id':self.replay_request})
            except queue.Full:
                # Retain held state; the normal UI poll retries without blocking Tk.
                return False
            except (ValueError,OSError):pass
        self.replay_held=False
        return True

    def stop_audio(self):
        self.replay_pending=None
        self.playback.stop()
        if not self.playback.playing:
            self.replay_token=None;self.release_replay()
        self.replay_status.set('回听已停止。采集中会自动恢复识别；可选择片段再次播放。')

    def poll_replay(self):
        while True:
            try:kind,payload=self.playback.events.get_nowait()
            except queue.Empty:break
            if payload.get('token')!=self.replay_token:continue
            self.replay_token=None
            if self.replay_pending is None:
                self.release_replay()
                self.replay_status.set('回听结束；采集中会自动恢复识别。' if kind!='error' else '播放失败：'+str(payload.get('message','输出设备不可用')))
        if self.replay_pending and time.monotonic()>self.replay_deadline:
            self.stop_audio();self.replay_status.set('等待识别暂停超时，未播放。可以停止采集后回听。')
        if self.replay_held and self.replay_token is None and self.replay_pending is None:self.release_replay()

    def render(self):
        records=self.captions.recent(self.keep_count.get())
        if (not records and not (self.reading_protect.get() and self.reader.pending)) or self.hidden:
            self.reader.suspend()
            self.overlay.hide();self.render_inputs=None;self.last_render=None; return
        rect, reason = self.get_layout()
        if not rect:
            self.reader.suspend()
            self.overlay.hide()
            self.render_inputs=None
            if self.last_render != reason:
                self.status.set(reason); self.last_render = reason
            return
        inputs=(tuple(rect),self.layout.get(),self.size.get(),self.max_lines.get(),
                tuple((r['id'],r['revision'],r['text'],r['final'],r.get('uncertain',False)) for r in records))
        if not self.reading_protect.get() and inputs==self.render_inputs and self.last_render is not None:return
        self.render_inputs=inputs
        font = self.overlay.font
        rows=max(1,min(self.max_lines.get(),(rect[3]-rect[1]-4)//font.metrics('linespace')))
        if self.reading_protect.get():
            lines,colors,state=self.reader.view(rect[2]-rect[0]-20,rows,font.measure,
                pace=1.5 if self.reading_pace.get()=='慢速阅读' else 1.0,keep=self.keep_count.get())
            label=('已暂停翻页' if state['paused'] else f"阅读保护 · 第 {state['page']} 页")+f" · {rows} 行 · 待阅读 {state['pending']} 段"
            if state['pending']:label+='；可点“追到最新”'
            if state['skipped']:label+=f"；积压过多，已移出字幕队列 {state['skipped']} 段，最近 40 段可在记录回看"
            self.visible_status.set(label)
        else:
            lines,colors,total=visible_lines(records,rect[2]-rect[0]-20,rows,font.measure)
            self.visible_status.set(f'实时跟随 · 保留 {len(records)} 段 · 当前区域 {rows} 行'+('；长句只显示末尾，可开启阅读保护。' if total>rows else ''))
        if not lines:self.overlay.hide();self.last_render=None;return
        signature = (tuple(rect),tuple(lines),tuple(colors),self.layout.get(),self.size.get())
        if signature != self.last_render:
            self.overlay.draw(rect,lines,self.layout.get(),self.size.get(),colors)
            self.last_render = signature

    def reading_changed(self):
        self.reader.reset()
        for record in self.captions.recent(self.keep_count.get(),seconds=120):self.reader.push(record)
        self.read_pause_button.configure(text='暂停翻页');self.last_render=None;self.save()

    def reading_pace_changed(self):
        self.reader.suspend();self.last_render=None;self.save()

    def pause_reading(self):
        if not self.reading_protect.get():self.reading_protect.set(True);self.reading_changed()
        paused=self.reader.pause();self.read_pause_button.configure(text='继续翻页' if paused else '暂停翻页')
        self.last_render=None

    def latest_reading(self):
        recent=list(self.captions.records.values())[-1:]
        self.reader.reset()
        for record in recent:self.reader.push(record)
        self.reader.latest();self.read_pause_button.configure(text='暂停翻页');self.last_render=None

    def poll(self):
        if self.closing:
            return
        for q in [self.ui_events,self.events]:
            if q is not self.ui_events and q is not self.events:continue
            for _ in range(25):
                try:
                    kind,payload = q.get_nowait()
                except (queue.Empty,ValueError,OSError):
                    break
                if q is not self.ui_events and self.process is None:
                    continue
                if kind in ('status','warning','error'):
                    self.status.set(payload)
                elif kind=='model_progress':
                    self.turbo_status.set(f'正在校验并安装 turbo：{payload}%')
                elif kind=='model_installed':
                    self.installing_model=False
                    self.install_model_button.configure(state='normal');self.start_button.configure(state='normal')
                    self.turbo_status.set('turbo 已安装' if turbo_ready() else 'turbo 未安装')
                    if payload:self.status.set('扩展安装失败：'+payload)
                    else:
                        self.speech_model.set('大模型 turbo');self.save()
                        self.status.set('turbo 扩展已安装，点击开始采集即可使用；没有自动开始采集。')
                elif kind == 'caption':
                    self.show_caption(payload)
                elif kind == 'screen_anchor':
                    self.set_screen_anchor(payload)
                elif kind == 'replay_ready':
                    self.begin_replay(payload.get('request_id'))
                elif kind == 'clear':
                    pass  # Preserve recent paragraphs when the source clears between sentences.
                elif kind == 'discard':
                    self.captions.records.pop(payload,None)
                    self.reader.discard(payload)
                    self.last_render=None
                    self.refresh_history()
                elif kind == 'finished':
                    # Retain the last caption briefly on natural completion.
                    if self.process and not self.process.is_alive():
                        self.process.join(timeout=0); self.process.close(); self.process=None
                        self.start_button.configure(text='开始采集')
                        self.stop_audio()
                elif kind == 'devices':
                    self.speakers, default = payload
                    self.audio_combo['values'] = [name for _,name in self.speakers]
                    if self.speakers:
                        self.audio_combo.current(next((i for i,(ident,_) in enumerate(self.speakers) if ident==default),0))
                elif kind == 'action':
                    self.action(payload)
                    if self.closing:return
        if self.process and not self.process.is_alive():
            self.process.join(timeout=0); self.process.close(); self.process=None
            self.start_button.configure(text='开始采集')
            self.stop_audio()
        self.poll_replay()
        self.render()
        self.root.after(150 if self.process else 350,self.poll)

    def action(self, action):
        if action=='read_pause':self.pause_reading();return
        if action=='read_latest':self.latest_reading();return
        if action=='toggle':
            self.layout.set('B' if self.layout.get()=='A' else 'A'); self.switch_layout()
        elif action=='pause':
            self.toggle_running()
        elif action=='hide':
            self.hidden = not self.hidden
            self.last_render = None
            self.status.set('字幕已暂隐，采集仍在运行。' if self.hidden else '字幕已恢复。')
        elif action=='settings':
            self.root.deiconify(); self.root.lift()
        elif action=='quit':
            self.quit()

    def setup_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
            icon = Image.new('RGB',(64,64),'#265c3b')
            draw=ImageDraw.Draw(icon);draw.rounded_rectangle((10,14,54,49),radius=6,outline='#e9f3db',width=4)
            draw.line((19,25,45,25), fill='#e9f3db',width=4);draw.line((19,37,38,37),fill='#e9f3db',width=4)
            def callback(name):
                return lambda *args: self.ui_events.put(('action',name))
            self.tray = pystray.Icon('suiyi',icon,'随译 · 本地字幕',pystray.Menu(
                pystray.MenuItem('显示面板',callback('settings'),default=True),
                pystray.MenuItem('切换 A / B',callback('toggle')),
                pystray.MenuItem('开始 / 停止',callback('pause')),
                pystray.MenuItem('隐藏 / 显示字幕',callback('hide')),
                pystray.MenuItem('退出',callback('quit'))))
            self.tray.run()
        except Exception as exc:
            self.ui_events.put(('warning',f'托盘不可用：{exc}；可用 Alt+Shift+S 找回面板。'))

    def minimize(self):
        if self.tray and self.tray.visible:
            self.root.withdraw()
        else:
            self.root.iconify()

    def quit(self):
        if self.installing_model:
            self.status.set('正在安装扩展，请等校验完成后退出；可以先收起到托盘。');return
        self.closing = True
        if self.dictionary is not None and not self.dictionary.closed:self.dictionary.close()
        self.dictionary_panel.close()
        self.stop()
        self.clips.clear()
        try:self.save()
        except OSError:self.root.report_callback_exception(*sys.exc_info())
        self.hotkeys.close()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

def main():
    mp.freeze_support()
    if '--self-test-screen' in sys.argv:
        from screen_check import self_test
        output=Path(sys.argv[sys.argv.index('--self-test-screen')+1])
        output.write_text(json.dumps(self_test(),ensure_ascii=False,indent=2),encoding='utf-8')
        return
    if '--self-test-libraries' in sys.argv:
        from public_checks import check_libraries
        output=Path(sys.argv[sys.argv.index('--self-test-libraries')+1])
        output.write_text(json.dumps(check_libraries(),ensure_ascii=False,indent=2),encoding='utf-8')
        return
    if '--self-test-workspace' in sys.argv:
        from workspace_check import self_test
        output=Path(sys.argv[sys.argv.index('--self-test-workspace')+1])
        output.write_text(json.dumps(self_test(),ensure_ascii=False,indent=2),encoding='utf-8')
        return
    if '--self-test-reading' in sys.argv:
        from reading import self_test
        output=Path(sys.argv[sys.argv.index('--self-test-reading')+1])
        output.write_text(json.dumps(self_test(),ensure_ascii=False,indent=2),encoding='utf-8')
        return
    if '--self-test-offline' in sys.argv:
        from bundle_test import main as self_test
        index=sys.argv.index('--self-test-offline')+1
        if index>=len(sys.argv) or sys.argv[index].startswith('--'):
            raise SystemExit('Usage: --self-test-offline OUTPUT.json')
        self_test(Path(sys.argv[index]),capture_loopback=False)
        return
    if '--self-test' in sys.argv:
        from bundle_test import main as self_test
        self_test()
        return
    if '--install-model' in sys.argv:
        report=settings_path().with_name('model-import-result.json')
        try:
            package=sys.argv[sys.argv.index('--install-model')+1]
            changed=install_pack(package)
            report.write_text(json.dumps({'ok':True,'changed':changed,'ready':turbo_ready()}),encoding='utf-8')
        except Exception as exc:
            report.write_text(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),encoding='utf-8')
            raise SystemExit(1)
        return
    native.dpi_aware()
    root=tk.Tk()
    def report_error(exc_type, exc, trace):
        import traceback
        log=settings_path().with_name('application.log')
        with log.open('a',encoding='utf-8') as stream:
            traceback.print_exception(exc_type,exc,trace,file=stream)
    root.report_callback_exception=report_error
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\SuiyiLocalSubtitlePrototype')
    if kernel.GetLastError() == 183:
        root.withdraw()
        messagebox.showinfo('随译', '随译已在运行，请用托盘图标或 Alt+Shift+S 显示面板。')
        root.destroy()
        return
    app=App(root)
    if '--smoke' in sys.argv:
        # Only verify panel startup; no capture starts without pressing Start.
        import faulthandler
        smoke_log=settings_path().with_name('startup-smoke.log').open('w',encoding='utf-8')
        smoke_log.write(repr(sys.argv)+'\n');smoke_log.flush()
        faulthandler.dump_traceback_later(10,file=smoke_log)
        root.after(3500,app.quit)
    root.mainloop()
    if mutex:
        kernel.CloseHandle(ctypes.c_void_p(mutex))

if __name__=='__main__':
    main()
