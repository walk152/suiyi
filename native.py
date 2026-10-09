"""Read-only window geometry, our own window styles and global hotkeys only."""
import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
import threading

u = c.windll.user32
_ENUMPROC = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)


def _prototype(name, result, *arguments):
    function = getattr(u, name)
    function.argtypes = list(arguments)
    function.restype = result


# A default ctypes signature treats HWND as a 32-bit int. Every window API
# needs an explicit pointer-sized signature in the 64-bit installed program.
for _name in ('IsWindow', 'IsIconic', 'IsWindowVisible', 'IsWindowEnabled'):
    _prototype(_name, w.BOOL, w.HWND)
_prototype('GetAncestor', w.HWND, w.HWND, w.UINT)
_prototype('GetWindowRect', w.BOOL, w.HWND, c.POINTER(w.RECT))
_prototype('GetClientRect', w.BOOL, w.HWND, c.POINTER(w.RECT))
_prototype('ClientToScreen', w.BOOL, w.HWND, c.POINTER(w.POINT))
_prototype('GetCursorPos', w.BOOL, c.POINTER(w.POINT))
_prototype('WindowFromPoint', w.HWND, w.POINT)
_prototype('IsChild', w.BOOL, w.HWND, w.HWND)
_prototype('GetWindowTextLengthW', c.c_int, w.HWND)
_prototype('GetWindowTextW', c.c_int, w.HWND, w.LPWSTR, c.c_int)
_prototype('EnumWindows', w.BOOL, _ENUMPROC, w.LPARAM)
_prototype('GetSystemMetrics', c.c_int, c.c_int)
_prototype('GetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int)
_prototype('SetWindowLongPtrW', c.c_ssize_t, w.HWND, c.c_int, c.c_ssize_t)
_prototype('SetWindowPos', w.BOOL, w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)
_prototype('SetWindowDisplayAffinity', w.BOOL, w.HWND, w.DWORD)
_prototype('RegisterHotKey', w.BOOL, w.HWND, c.c_int, w.UINT, w.UINT)
_prototype('UnregisterHotKey', w.BOOL, w.HWND, c.c_int)
_prototype('GetMessageW', w.BOOL, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
_prototype('PostThreadMessageW', w.BOOL, w.DWORD, w.UINT, w.WPARAM, w.LPARAM)
for _name in ('SetProcessDpiAwarenessContext', 'SetThreadDpiAwarenessContext'):
    try:
        _prototype(_name, w.BOOL if _name.startswith('SetProcess') else c.c_void_p, c.c_void_p)
    except AttributeError:
        pass
c.windll.kernel32.GetCurrentThreadId.argtypes = []
c.windll.kernel32.GetCurrentThreadId.restype = w.DWORD


@contextmanager
def _pixel_coordinates():
    """Temporarily avoid DPI virtualization; restore the caller's UI context."""
    setter = getattr(u, 'SetThreadDpiAwarenessContext', None)
    previous = setter(c.c_void_p(-4)) if setter is not None else None
    try:
        yield
    finally:
        if previous:
            setter(previous)

def dpi_aware():
    try:
        u.SetProcessDpiAwarenessContext(c.c_void_p(-4))
    except Exception:
        pass

def desktop():
    """Virtual desktop bounds, including monitors left/above the primary one."""
    with _pixel_coordinates():
        left, top = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        return [left, top, left+u.GetSystemMetrics(78), top+u.GetSystemMetrics(79)]


def primary_screen():
    with _pixel_coordinates():
        return [0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)]


def _available(hwnd):
    return bool(hwnd and u.IsWindow(hwnd) and not u.IsIconic(hwnd) and u.IsWindowVisible(hwnd))


def _valid_rect(rect):
    return rect if rect[2] > rect[0] and rect[3] > rect[1] else None

def window_rect(hwnd):
    """Full window bounds; deliberately unclipped for saved relative regions."""
    if not _available(hwnd):
        return None
    with _pixel_coordinates():
        r = w.RECT()
        if not u.GetWindowRect(hwnd, c.byref(r)):
            return None
        return _valid_rect([r.left, r.top, r.right, r.bottom])


def client_rect(hwnd):
    """Visible client bounds in physical screen pixels, excluding the title bar.

    This is geometry only: obscured content is not recovered from other apps.
    None means hidden, minimized, closed, zero-sized, or outside the desktop.
    """
    if not _available(hwnd):
        return None
    with _pixel_coordinates():
        rect = w.RECT()
        if not u.GetClientRect(hwnd, c.byref(rect)):
            return None
        first, last = w.POINT(rect.left, rect.top), w.POINT(rect.right, rect.bottom)
        if not u.ClientToScreen(hwnd, c.byref(first)) or not u.ClientToScreen(hwnd, c.byref(last)):
            return None
        # Mirrored windows may map the two horizontal edges in reverse order.
        left, right = sorted((first.x, last.x))
        top, bottom = sorted((first.y, last.y))
        bounds = desktop()
        return _valid_rect([max(left, bounds[0]), max(top, bounds[1]),
                            min(right, bounds[2]), min(bottom, bounds[3])])


def cursor_position():
    """Current pointer position in physical virtual-desktop pixels, or None."""
    with _pixel_coordinates():
        point = w.POINT()
        if not u.GetCursorPos(c.byref(point)):
            return None
        return point.x, point.y


def _contains(rect, point):
    return bool(rect and rect[0] <= point[0] < rect[2] and rect[1] <= point[1] < rect[3])


def _click_through(hwnd):
    # Layered + transparent is the OS mouse pass-through combination used by
    # our subtitle overlay. This also works from the separate capture process.
    return u.GetWindowLongPtrW(hwnd, -20) & 0x80020 == 0x80020


def point_belongs_to_window(hwnd, point):
    """Check that a client-area point hits this window or one of its children.

    Another application's occluding window is rejected. A transparent subtitle
    overlay does not suppress hover detection. No messages are sent to the
    target process and no screenshots are taken by this helper.
    """
    if point is None or not _contains(client_rect(hwnd), point):
        return False
    with _pixel_coordinates():
        hit = u.WindowFromPoint(w.POINT(int(point[0]), int(point[1])))
        if not hit:
            return False
        root = u.GetAncestor(hit, 2) or hit
        if _click_through(root):
            # Normally WindowFromPoint already skips these overlays. Some
            # layered-window backends report the overlay itself; walk the
            # bounded EnumWindows snapshot instead of using a GetWindow loop.
            found = []
            @_ENUMPROC
            def visit(candidate, _):
                if (_available(candidate) and u.IsWindowEnabled(candidate)
                        and not _click_through(candidate)
                        and _contains(window_rect(candidate), point)):
                    found.append(candidate)
                    return False
                return True
            u.EnumWindows(visit, 0)
            hit = found[0] if found else None
        return bool(hit and (hit == hwnd or u.IsChild(hwnd, hit)))

def windows():
    items = []
    @_ENUMPROC
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            buf = c.create_unicode_buffer(n+1)
            u.GetWindowTextW(hwnd, buf, n+1)
            title = buf.value
            rect = window_rect(hwnd)
            if title and rect and rect[2]-rect[0] > 150 and rect[3]-rect[1] > 100 and not title.startswith('随译'):
                items.append((int(hwnd), title))
        return True
    u.EnumWindows(visit, 0)
    return items

def style_overlay(toplevel):
    hwnd = u.GetAncestor(toplevel.winfo_id(), 2)
    flags = u.GetWindowLongPtrW(hwnd, -20)
    u.SetWindowLongPtrW(hwnd, -20, flags | 0x80000 | 0x20 | 0x08000000 | 0x80)
    # Mouse click-through, never activate; only our own HWND is touched.
    u.SetWindowPos(hwnd, w.HWND(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10 | 0x20)
    return bool(u.SetWindowDisplayAffinity(hwnd, 0x11))

class Hotkeys:
    def __init__(self, callback):
        self.callback = callback
        self.ident = None
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        self.ident = c.windll.kernel32.GetCurrentThreadId()
        names = {1: ('T', 'toggle'), 2: ('P', 'pause'), 3: ('H', 'hide'), 4: ('S', 'settings'),5:('R','read_pause'),6:('L','read_latest')}
        registered = []
        for key, (letter, action) in names.items():
            if u.RegisterHotKey(None, key, 0x1 | 0x4 | 0x4000, ord(letter)):
                registered.append(key)
            else:
                self.callback('warning', f'快捷键 Alt+Shift+{letter} 被占用，请使用面板或托盘。')
        msg = w.MSG()
        try:
            while u.GetMessageW(c.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x312:
                    self.callback('action', names[msg.wParam][1])
        finally:
            for key in registered:
                u.UnregisterHotKey(None, key)

    def close(self):
        if self.ident:
            u.PostThreadMessageW(self.ident, 0x12, 0, 0)
