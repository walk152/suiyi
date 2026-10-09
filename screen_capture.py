"""Bounded screen sampling and dwell selection; no target application hooks."""
from collections import OrderedDict
import math
import queue
import time


class HoverTracker:
    def __init__(self, delay=1.5, tolerance=7):
        self.delay, self.tolerance = delay, tolerance
        self.anchor = None
        self.since = 0.
        self.generation = 0

    def update(self, point, now, eligible=True):
        if not eligible or point is None:
            if self.anchor is not None:
                self.generation += 1
            self.anchor = None
            return False
        if self.anchor is None or math.dist(self.anchor, point) > self.tolerance:
            self.anchor, self.since = tuple(point), now
            self.generation += 1
        return now - self.since >= self.delay


def intersect(a, b):
    if not a or not b:
        return None
    r = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    return r if r[2]-r[0] >= 2 and r[3]-r[1] >= 2 else None


def hover_crop(bounds, point, width=1800, height=600):
    width, height = min(width, bounds[2]-bounds[0]), min(height, bounds[3]-bounds[1])
    left = max(bounds[0], min(point[0]-width//2, bounds[2]-width))
    top = max(bounds[1], min(point[1]-height//2, bounds[3]-height))
    return [int(left), int(top), int(left+width), int(top+height)]


def actual_region(cfg, point=None):
    import native
    from core import absolute_rect
    window = native.window_rect(cfg.get('hwnd'))
    client = native.client_rect(cfg.get('hwnd'))
    if not window or not client:
        return None
    mode = cfg.get('screen_mode', 'auto')
    if mode == 'region':
        relative = cfg.get('roi_relative')
        return intersect(absolute_rect(relative, window), client) if relative else None
    return hover_crop(client, point) if mode == 'hover' and point else client


def image_changed(previous, current):
    import numpy as np
    if previous is None or previous.shape != current.shape:
        return True
    delta = np.abs(previous.astype('int16') - current.astype('int16'))
    # Small text changes on a large mostly-static page must also trigger OCR.
    return bool(delta.mean() > .4 or (delta > 18).mean() > .001)


def capture_screen(cfg, stopped, emit, translator, controls=None):
    import mss
    import numpy as np
    import native
    from PIL import Image
    from engine import make_ocr
    from learning import LearningSession
    from screen_text import read_scene, choose_nearest

    mode = cfg.get('screen_mode', 'auto')
    if mode not in ('auto', 'hover', 'region'):
        raise ValueError('未知画面识别方式，请重新选择。')
    learning = LearningSession(cfg.get('speech_profile', 'general'), cfg.get('language', 'en'))
    emit('status', '正在加载本地文字识别模型…')
    ocr = make_ocr()
    tracker = HoverTracker()
    last_image = last_rect = None
    last_check = 0.
    last_status = ''
    blocks, obstacles, pending = [], [], []
    seen = OrderedDict()
    session = time.monotonic_ns()
    sequence = 0
    last_selection = None
    retry_at = 0.

    def status(message):
        nonlocal last_status
        if message != last_status:
            emit('status', message)
            last_status = message

    def hide_anchor():
        emit('screen_anchor', None)

    def still_current(rect, generation, window):
        if stopped.is_set() or native.window_rect(cfg['hwnd']) != window:
            return False
        if mode == 'hover':
            point = native.cursor_position()
            return (point is not None and tracker.anchor is not None
                    and math.dist(point, tracker.anchor) <= tracker.tolerance
                    and native.point_belongs_to_window(cfg['hwnd'], point)
                    and tracker.generation == generation and actual_region(cfg, tracker.anchor) == rect)
        return actual_region(cfg) == rect

    status('鼠标停留 1.5 秒后翻译附近句子。' if mode == 'hover'
           else '正在自动识别窗口文字。' if mode == 'auto' else '正在识别框选区域。')
    with mss.mss() as capture:
        while not stopped.is_set():
            now = time.monotonic()
            if controls is not None:
                while True:
                    try:
                        update = controls.get_nowait()
                    except queue.Empty:
                        break
                    if any(k in update for k in ('speech_profile', 'reload_memory')):
                        learning = LearningSession(update.get('speech_profile', learning.profile), cfg.get('language', 'en'))
                        last_image = None
                        seen.clear()
            point = native.cursor_position() if mode == 'hover' else None
            if mode == 'hover':
                generation = tracker.generation
                ready = tracker.update(point, now, native.point_belongs_to_window(cfg['hwnd'], point))
                if generation != tracker.generation:
                    hide_anchor()
                    last_image = last_rect = None
                    last_selection = None
                    pending = []
                if not ready:
                    status('鼠标停留 1.5 秒后翻译附近句子。')
                    stopped.wait(.08)
                    continue
            rect = actual_region(cfg, tracker.anchor if mode == 'hover' else None)
            if not rect:
                hide_anchor()
                last_image = last_rect = None
                pending = []
                status('目标窗口不可见或已最小化，请恢复窗口；关闭后需要刷新并重新选择。')
                stopped.wait(.8)
                continue
            if now < retry_at:
                stopped.wait(.1)
                continue
            # No screenshots while the pointer is moving; static scenes only
            # receive a cheap thumbnail comparison, not repeated model calls.
            if now - last_check < (1. if mode == 'hover' else .85):
                stopped.wait(.08)
                continue
            start = time.monotonic()
            last_check = start
            generation = tracker.generation
            window = native.window_rect(cfg['hwnd'])
            try:
                frame = capture.grab(dict(left=rect[0], top=rect[1], width=rect[2]-rect[0], height=rect[3]-rect[1]))
                rgb = Image.frombytes('RGB', frame.size, frame.rgb)
                thumbnail = np.asarray(rgb.resize((480, max(60, round(480*rgb.height/rgb.width)))).convert('L'))
                changed = rect != last_rect or image_changed(last_image, thumbnail)
                if changed:
                    blocks, obstacles = read_scene(ocr, rgb, cfg.get('language', 'en'))
                    if not still_current(rect, generation, window):
                        hide_anchor()
                        last_image = None
                        continue
                    last_image, last_rect = thumbnail, list(rect)
                    pending = list(blocks)
                    if not blocks:
                        hide_anchor()
                        last_selection = None
                        status('未找到可翻译的原文；请核对翻译方向、放大文字，或使用框选区域。')
                if mode == 'hover':
                    selected = choose_nearest(blocks, (tracker.anchor[0]-rect[0], tracker.anchor[1]-rect[1]), 100.)
                    pending = [selected] if selected else []
                    if not selected:
                        hide_anchor()
                        status('鼠标附近没有找到对应语言的句子，请移近原文。')
                processed = 0
                occluded = 0
                while pending and not stopped.is_set() and processed < 4:
                    block = pending.pop(0)
                    box = [round(v+rect[i % 2]) for i, v in enumerate(block['box'])]
                    midpoint = ((box[0]+box[2])//2, (box[1]+box[3])//2)
                    # Visible-screen capture cannot recover content hidden by
                    # another app. Do not translate that app as our target.
                    if not native.point_belongs_to_window(cfg['hwnd'], midpoint):
                        occluded += 1
                        continue
                    key = (block['text'], tuple(round(v/4) for v in box))
                    if mode == 'hover' and key == last_selection:
                        continue
                    if mode != 'hover' and key in seen and now-seen[key] < 45:
                        continue
                    raw = block['text']
                    text, learned = learning.correct(raw)
                    output = translator.translate(text) if translator else text
                    if not output:
                        raise RuntimeError('模型没有返回译文，请缩小识别范围后重试。')
                    if not still_current(rect, generation, window):
                        hide_anchor()
                        last_image = None
                        pending = []
                        break
                    sequence += 1
                    blocked = [[round(v+rect[i % 2]) for i, v in enumerate(b)] for b in obstacles]
                    emit('caption', dict(source=text, text=output, raw_source=raw, learned=learned,
                         cost=time.monotonic()-start, kind='鼠标取句' if mode == 'hover' else '画面',
                         id=f'screen-{session}-{sequence}', final=True, screen_mode=mode,
                         source_rect=box, blocked_rects=blocked, capture_window_rect=window))
                    last_selection = key
                    seen[key] = now
                    while len(seen) > 200:
                        seen.popitem(last=False)
                    processed += 1
                    last_status = ''
                if occluded and not processed:
                    hide_anchor()
                    last_image = None
                    status('目标文字被其他窗口遮挡，请将所选窗口置前。')
            except Exception as exc:
                # Retry at a bounded rate; a single bad capture or OCR frame
                # must not leave an apparently running but inert process.
                last_image = None
                hide_anchor()
                status('画面处理暂未成功，将重试：'+str(exc)[:180])
                retry_at = time.monotonic()+2.
            stopped.wait(.08)
