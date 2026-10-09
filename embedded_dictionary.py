"""Small offline dictionary card; workers never touch Tk and pending work is bounded."""
from collections import OrderedDict
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

from lexicon import format_result, lookup, normalize


DEFAULT_PALETTE = {
    'bg': '#f5f3ed', 'card': '#fffdf7', 'text': '#263c38',
    'muted': '#737d73', 'accent': '#417466', 'border': '#dce1d5',
    'nav': '#edf1e8',
}

# A lock coalesces requests from the floating and embedded dictionaries. The
# bounded cache holds formatted text, with no persistent database connections.
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 96
_CACHE_MAX_TEXT = 16384


def clear_lookup_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def cached_lookup(query):
    key = normalize(query)
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        result = format_result(lookup(key))
        if len(result) <= _CACHE_MAX_TEXT:
            _CACHE[key] = result
            while len(_CACHE) > _CACHE_LIMIT:
                _CACHE.popitem(last=False)
        return result


class DictionaryPanel:
    """Embed ``frame`` with pack/grid; public methods run on the Tk thread."""
    def __init__(self, parent, add_name, palette=None):
        self.closed = False
        self.busy = False
        self.pending = None
        self._generation = 0
        self._after_id = None
        self._raw_context = ''
        self.events = queue.Queue(maxsize=2)
        self._add_name = add_name
        self.palette = dict(DEFAULT_PALETTE)
        self.query = tk.StringVar(parent)
        self.context = tk.StringVar(parent)
        self.frame = tk.Frame(parent, width=280, height=330, bd=0)
        self.frame.columnconfigure(0, weight=1, minsize=248)
        self.frame.rowconfigure(2, weight=1)
        self.row = tk.Frame(self.frame, bd=0)
        self.row.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.row.columnconfigure(0, weight=1)
        self.entry = tk.Entry(
            self.row, textvariable=self.query, font=('Microsoft YaHei UI', -16),
            bd=0, highlightthickness=1, relief='flat', width=12,
        )
        self.entry.grid(row=0, column=0, sticky='ew', ipady=7)
        self.entry.bind('<Return>', lambda _event: self.search())
        self.button = tk.Button(
            self.row, text='查词', command=self.search, bd=0, padx=14, pady=6,
            cursor='hand2', font=('Microsoft YaHei UI', -15),
        )
        self.button.grid(row=0, column=1, padx=(8, 0))
        self.context_label = tk.Label(
            self.frame, textvariable=self.context, anchor='nw', justify='left',
            font=('Microsoft YaHei UI', -13), height=2, bd=0,
        )
        self.context_label.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        self.context_label.grid_remove()
        self.result_frame = tk.Frame(self.frame, bd=0)
        self.result_frame.grid(row=2, column=0, sticky='nsew')
        self.output = tk.Text(
            self.result_frame, wrap='word', font=('Microsoft YaHei UI', -16),
            state='disabled', bd=0, highlightthickness=0, padx=6, pady=8,
            height=10, width=24, spacing1=3, spacing3=5, exportselection=False,
        )
        self.output.pack(side='left', fill='both', expand=True)
        self.scroll = tk.Scrollbar(
            self.result_frame, command=self.output.yview, bd=0, width=12,
            highlightthickness=0,
        )
        self.scroll.pack(side='right', fill='y')
        self.output.configure(yscrollcommand=self.scroll.set)
        self.footer = tk.Frame(self.frame, bd=0)
        self.footer.grid(row=3, column=0, sticky='ew', pady=(9, 0))
        self.credit = tk.Label(
            self.footer, text='ECDICT · 离线词典', anchor='w',
            font=('Microsoft YaHei UI', -13), bd=0,
        )
        self.credit.pack(side='left')
        self.name_button = tk.Button(
            self.footer, text='加入专名', command=self.add_current_name,
            bd=0, padx=7, pady=4, cursor='hand2', font=('Microsoft YaHei UI', -13),
        )
        self.name_button.pack(side='right')
        self._context_font = tkfont.Font(self.frame, family='Microsoft YaHei UI', size=-13)
        self.frame.bind('<Configure>', self._on_resize, add='+')
        self.frame.bind('<Destroy>', self._on_destroy, add='+')
        self.apply_theme(palette or {})
        self.set_text('双击英文单词即可查词。\n\n也可以在上方输入单词或短语。\n\n释义来自本地词典；人名未收录时，可加入专名提示。')

    def show_query(self, query, context=''):
        if self.closed:
            return
        self.query.set(query)
        self._raw_context = ' '.join(str(context).split())[:320]
        self._render_context()
        self.search()

    def search(self):
        if self.closed:
            return
        self._generation += 1
        request = (self._generation, self.query.get())
        self.set_text('正在查本地词典…')
        if self.busy:
            self.pending = request
        else:
            self._start(request)

    def _start(self, request):
        self.busy = True
        # Capture only an ordinary queue, never widgets or Tk variables.
        events = self.events

        def work():
            generation, query = request
            try:
                result = cached_lookup(query)
            except Exception as exc:
                result = '查词失败：' + str(exc)
            try:
                events.put_nowait((generation, result))
            except queue.Full:
                pass

        threading.Thread(target=work, daemon=True, name='suiyi-dictionary').start()
        self._schedule_poll()

    def _schedule_poll(self):
        if self.busy and not self.closed and self._after_id is None:
            self._after_id = self.frame.after(60, self.poll)

    def poll(self):
        self._after_id = None
        if self.closed:
            return
        try:
            generation, result = self.events.get_nowait()
            self.busy = False
            if self.pending is not None:
                request, self.pending = self.pending, None
                self._start(request)
            elif generation == self._generation:
                self.set_text(result)
        except queue.Empty:
            pass
        self._schedule_poll()

    def set_text(self, text):
        if self.closed:
            return
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('end', text)
        self.output.configure(state='disabled')
        self.output.yview_moveto(0)

    def add_current_name(self):
        query = self.query.get().strip()
        if query and not self.closed:
            self._add_name(query)

    def _on_resize(self, _event):
        if not self.closed:
            self._render_context()

    def _render_context(self):
        if not self._raw_context:
            self.context.set('')
            self.context_label.grid_remove()
            return
        self.context_label.grid()
        width = max(210, self.frame.winfo_width() - 8)
        remaining = '上下文 · ' + self._raw_context
        lines = []
        for row in range(2):
            line = ''
            while remaining and self._context_font.measure(line + remaining[0]) < width:
                line += remaining[0]
                remaining = remaining[1:]
            if row == 1 and remaining:
                while line and self._context_font.measure(line + '…') > width:
                    line = line[:-1]
                line += '…'
            lines.append(line)
            if not remaining:
                break
        self.context.set('\n'.join(lines))

    def apply_theme(self, palette):
        if self.closed:
            return
        self.palette.update({key: value for key, value in palette.items() if value})
        p = self.palette
        for widget in (self.frame, self.row, self.result_frame, self.footer):
            widget.configure(bg=p['card'])
        for widget in (self.credit, self.context_label):
            widget.configure(bg=p['card'], fg=p['muted'])
        self.entry.configure(
            bg=p['bg'], fg=p['text'], insertbackground=p['text'],
            highlightbackground=p['border'], highlightcolor=p['accent'],
            selectbackground=p['accent'], selectforeground='white',
        )
        self.button.configure(
            bg=p['accent'], fg='white', activebackground=p['text'],
            activeforeground='white', disabledforeground=p['muted'],
        )
        self.name_button.configure(
            bg=p['nav'], fg='white', activebackground=p['border'],
            activeforeground=p['text'],
        )
        self.output.configure(
            bg=p['card'], fg=p['text'], insertbackground=p['text'],
            selectbackground=p['accent'], selectforeground='white',
        )
        self.scroll.configure(bg=p['border'], troughcolor=p['card'], activebackground=p['muted'])

    def _on_destroy(self, event):
        if event.widget is self.frame:
            self._dispose()

    def _dispose(self):
        if self.closed:
            return
        self.closed = True
        self.pending = None
        self.busy = False
        if self._after_id is not None:
            try:
                self.frame.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def close(self):
        if self.closed:
            return
        self._dispose()
        self.frame.destroy()
