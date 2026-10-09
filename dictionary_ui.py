"""Non-modal dictionary window using the embedded card's offline lookup/cache."""
import tkinter as tk

from embedded_dictionary import DEFAULT_PALETTE, DictionaryPanel


class DictionaryWindow:
    def __init__(self, root, add_name, palette=None):
        self.closed = False
        self.win = tk.Toplevel(root)
        self.win.title('随译 · 小词典')
        self.win.geometry('480x430')
        self.win.minsize(350, 300)
        self.win.transient(root)
        self.panel = DictionaryPanel(self.win, add_name, palette)
        self.panel.frame.pack(fill='both', expand=True, padx=18, pady=18)
        self.apply_theme(palette or DEFAULT_PALETTE)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.win.bind('<Escape>', lambda _event: self.close())
        self.win.bind('<Destroy>', self._on_destroy, add='+')

    def __getattr__(self, name):
        # Older integrations use .busy/.output/.entry/.query/.search directly.
        panel = self.__dict__.get('panel')
        if panel is not None:
            return getattr(panel, name)
        raise AttributeError(name)

    def show(self, query='', context=''):
        if self.closed:
            return
        self.win.deiconify()
        self.win.lift()
        self.panel.entry.focus_set()
        if query:
            self.panel.show_query(query, context)

    def apply_theme(self, palette):
        if self.closed:
            return
        self.panel.apply_theme(palette)
        self.win.configure(bg=self.panel.palette['card'])

    def _on_destroy(self, event):
        if event.widget is self.win:
            self.closed = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.panel.close()
        self.win.destroy()
