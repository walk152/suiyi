"""Explicit, reversible personal corrections and built-in name lookup."""
import tkinter as tk
from tkinter import ttk, messagebox
from learning import LearningStore, catalog

class LearningWindow:
    def __init__(self, root, profile, language, changed, source=''):
        self.store=LearningStore();self.profile=profile;self.language=language;self.changed=changed
        self.win=tk.Toplevel(root);self.win.title('随译 · 角色词库与学习记忆')
        self.win.geometry('760x670');self.win.minsize(620,530)
        box=ttk.Frame(self.win,padding=14);box.pack(fill='both',expand=True)
        label='重返未来：1999' if profile=='1999' else '通用'
        ttk.Label(box,text=f'当前记忆：{label} / {language} · 完全本地，最多保留最近 1000 条').pack(anchor='w')
        book=ttk.Notebook(box);book.pack(fill='both',expand=True,pady=8)
        names=ttk.Frame(book,padding=10);memo=ttk.Frame(book,padding=10)
        book.add(names,text='内置 1999 人名');book.add(memo,text='纠错与记忆')
        self.query=tk.StringVar();entry=ttk.Entry(names,textvariable=self.query);entry.pack(fill='x')
        self.query.trace_add('write',lambda *a:self.filter_names())
        ttk.Label(names,text='搜索英文名或已收录的中文别名。双击加入当前记忆，作为辨音提示。',wraplength=640).pack(anchor='w',pady=5)
        self.names=tk.Listbox(names,font=('Microsoft YaHei UI',11),exportselection=False)
        self.names.pack(fill='both',expand=True);self.names.bind('<Double-Button-1>',lambda e:self.add_selected())
        ttk.Button(names,text='记住选中人名',command=self.add_selected).pack(anchor='w',pady=6)
        ttk.Label(names,text='140 个索引项，非全部 NPC。普通词与短名字需手动选中；不会强行替换。 '
                  '索引：Prydwen 角色页 / R1999 Logs；版本 2026-10-05。',wraplength=640).pack(anchor='w')
        self.kind=tk.StringVar(value='整句纠错')
        ttk.Combobox(memo,textvariable=self.kind,values=['整句纠错','专名提示'],state='readonly').pack(anchor='w')
        ttk.Label(memo,text='原识别句（整句纠错时使用；可从最近字幕带入）').pack(anchor='w',pady=(6,2))
        self.source=tk.Text(memo,height=3,wrap='word');self.source.pack(fill='x');self.source.insert('1.0',source)
        ttk.Label(memo,text='正确内容 / 正确人名').pack(anchor='w',pady=(6,2))
        self.target=tk.Text(memo,height=3,wrap='word');self.target.pack(fill='x')
        ttk.Button(memo,text='保存这条记忆',command=self.save).pack(anchor='w',pady=6)
        ttk.Label(memo,text='整句纠错仅在原句词序完全匹配时应用，忽略大小写和标点；已应用会标注。 '
                  '专名只辅助识别。不会把存疑字幕自动当作正确答案，也不会在后台训练大模型。',wraplength=640).pack(anchor='w')
        self.memories=tk.Listbox(memo,font=('Microsoft YaHei UI',10),exportselection=False)
        self.memories.pack(fill='both',expand=True,pady=7)
        ttk.Button(memo,text='删除选中记忆 / 撤销学习',command=self.remove).pack(anchor='w')
        self.status=tk.StringVar(value='只保存你确认的文字，不保存录音。')
        ttk.Label(box,textvariable=self.status,wraplength=700).pack(anchor='w')
        self.filter_names();self.refresh()
        if source:book.select(memo)

    def filter_names(self):
        q=self.query.get().strip().casefold()
        self.filtered=[x for x in catalog() if q in (x['en']+' '+x['zh']).casefold()]
        self.names.delete(0,'end')
        for x in self.filtered:self.names.insert('end',x['en']+(' · '+x['zh'] if x['zh'] else '')+('  [手动提示]' if not x['auto'] else ''))

    def refresh(self):
        self.rows=self.store.rows(self.profile,self.language);self.memories.delete(0,'end')
        for x in self.rows:self.memories.insert('end',('专名：' if x['kind']=='name' else x['source']+' → ')+x['target'])

    def add_selected(self):
        selected=self.names.curselection()
        if not selected:return
        name=self.filtered[selected[0]]['en']
        self.store.remember(self.profile,self.language,'name','',name);self.finish_change('已记住：'+name)

    def save(self):
        try:
            self.store.remember(self.profile,self.language,'name' if self.kind.get()=='专名提示' else 'sentence',
                                self.source.get('1.0','end').strip(),self.target.get('1.0','end').strip())
            self.finish_change('已保存；下一段识别生效。')
        except (OSError,ValueError) as exc:messagebox.showerror('未保存',str(exc),parent=self.win)

    def remove(self):
        selected=self.memories.curselection()
        if not selected:return
        self.store.forget(self.profile,self.language,self.rows[selected[0]]);self.finish_change('已删除，后续不再使用这条记忆。')

    def finish_change(self,text):
        self.refresh();self.changed();self.status.set(text)
