"""Spacious native workspace; appearance changes never rebuild capture state."""
import tkinter as tk
from tkinter import ttk

PALETTES = {
    'vertin': dict(bg='#F0F1EB', card='#FFFFFF', text='#253B37', muted='#73817A',
                   accent='#486956', border='#D9E0D8', nav='#203B35', soft='#E6EDE5'),
    'ryuko': dict(bg='#F1F2F7', card='#FFFFFF', text='#232B44', muted='#7B8091',
                  accent='#BB3453', border='#DDE0EA', nav='#20243A', soft='#F4E6EC'),
}
THEMES = {'vertin': ('雨幕', 'RAIN / LISTEN & LEARN'), 'ryuko': ('赤色节拍', 'SCARLET / LISTEN & LEARN')}


class Workspace:
    def __init__(self, app, modes, speech_models, profiles):
        self.app = a = app
        self.root = a.root
        self.colors = []
        self.images = {}
        self.pages = {}
        self.buttons = {}
        self.current = 'work'
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self.shell = self.frame(self.root, 'bg')
        self.shell.pack(fill='both', expand=True)
        self.shell.columnconfigure(1, weight=1)
        self.shell.rowconfigure(0, weight=1)
        nav = self.frame(self.shell, 'nav', width=174)
        nav.grid(row=0, column=0, sticky='ns')
        nav.pack_propagate(False)
        self.label(nav, '随译', bg='nav', fg='white', size=27, bold=True).pack(anchor='w', padx=25, pady=(30, 0))
        self.label(nav, 'SUIYI / LOCAL', bg='nav', fg='#AFC2B8', size=9).pack(anchor='w', padx=26, pady=(2, 35))
        for key, title in [('work','文本与回听'), ('sound','声音与识别'), ('captions','字幕与阅读'), ('themes','外观主题')]:
            button = tk.Button(nav, text=title, font=('Microsoft YaHei UI',-16), bd=0, anchor='w',
                               padx=22, pady=15, cursor='hand2', command=lambda k=key:self.show(k))
            button.pack(fill='x', padx=10, pady=3)
            self.buttons[key] = button
        self.label(nav, '学习工具', bg='nav', fg='#AFC2B8', size=9).pack(anchor='w', padx=26, pady=(30,8))
        for text, fn in [('词库与记忆', a.open_learning), ('打开小词典', a.open_dictionary)]:
            b = tk.Button(nav, text=text, font=('Microsoft YaHei UI',-15), bd=0, anchor='w', padx=24,
                          pady=12, cursor='hand2', command=fn)
            b.pack(fill='x', padx=10)
            self.colors.append((b, {'bg':'nav','fg':'white','activebackground':'accent','activeforeground':'white'}))
        bottom = self.frame(nav, 'nav'); bottom.pack(side='bottom', fill='x', padx=22, pady=23)
        for text, fn in [('收起到托盘', a.minimize), ('退出随译', a.quit)]:
            b = tk.Button(bottom, text=text, bd=0, font=('Microsoft YaHei UI',-13), anchor='w', pady=8, command=fn)
            b.pack(fill='x'); self.colors.append((b, {'bg':'nav','fg':'#C1CEC8','activebackground':'accent','activeforeground':'white'}))
        main = self.frame(self.shell, 'bg'); main.grid(row=0,column=1,sticky='nsew',padx=24,pady=23)
        main.columnconfigure(0,weight=1); main.rowconfigure(2,weight=1)
        heading = self.frame(main,'bg'); heading.grid(row=0,column=0,sticky='ew')
        self.title = self.label(heading,'文本与回听',bg='bg',size=24,bold=True); self.title.pack(side='left')
        a.start_button = ttk.Button(heading,text='开始采集',style='Accent.TButton',command=a.toggle_running)
        a.start_button.pack(side='right',pady=4)
        state = self.label(main,bg='bg',fg='muted',textvariable=a.status,wraplength=760,size=10,justify='left',anchor='w')
        state.grid(row=1,column=0,sticky='ew',pady=(9,18))
        main.bind('<Configure>',lambda e:state.configure(wraplength=max(250,e.width-6)))
        self.host = self.frame(main,'bg'); self.host.grid(row=2,column=0,sticky='nsew')
        self.host.rowconfigure(0,weight=1);self.host.columnconfigure(0,weight=1)
        for key in self.buttons:
            page=self.frame(self.host,'bg');page.grid(row=0,column=0,sticky='nsew');self.pages[key]=page

        # Text and listening are a dedicated workspace, with no settings mixed in.
        work=self.pages['work'];work.columnconfigure(0,weight=1);work.rowconfigure(1,weight=1)
        source=self.card(work);source.grid(row=0,column=0,sticky='ew',pady=(0,14));source.columnconfigure(0,weight=1)
        self.label(source,'采集目标',size=11,bold=True).grid(row=0,column=0,sticky='w',pady=(0,8))
        a.window_combo=ttk.Combobox(source,state='readonly');a.window_combo.grid(row=1,column=0,sticky='ew')
        a.window_combo.bind('<<ComboboxSelected>>',a.select_window)
        ttk.Button(source,text='刷新窗口',command=a.refresh_windows).grid(row=1,column=1,padx=(8,0))
        a.mode_combo=ttk.Combobox(source,values=list(modes),textvariable=a.mode,state='readonly')
        a.mode_combo.grid(row=2,column=0,sticky='ew',pady=(9,0));a.mode_combo.bind('<<ComboboxSelected>>',lambda e:a.input_changed())
        ttk.Button(source,text='字幕位置',command=lambda:self.show('captions')).grid(row=2,column=1,padx=(8,0),pady=(9,0))
        a.screen_mode_combo=ttk.Combobox(source,values=list(a.screen_methods.values()),textvariable=a.screen_method,state='readonly')
        a.screen_mode_combo.grid(row=3,column=0,sticky='ew',pady=(9,0))
        a.screen_mode_combo.bind('<<ComboboxSelected>>',lambda e:a.screen_method_changed())
        a.screen_pick_button=ttk.Button(source,text='框选区域',command=lambda:a.pick('roi'))
        a.screen_pick_button.grid(row=3,column=1,padx=(8,0),pady=(9,0))
        source_hint=self.label(source,textvariable=a.screen_hint,fg='muted',size=9,justify='left',anchor='w',wraplength=500)
        source_hint.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(7,0))
        source.bind('<Configure>',lambda e:source_hint.configure(wraplength=max(200,e.width-36)))
        a.update_screen_controls()
        textcard=self.card(work);textcard.grid(row=1,column=0,sticky='nsew');textcard.columnconfigure(0,weight=1);textcard.rowconfigure(2,weight=1)
        row=self.frame(textcard);row.grid(row=0,column=0,columnspan=2,sticky='ew')
        self.label(row,'实时文本',size=15,bold=True).pack(side='left')
        ttk.Button(row,text='纠正最近一句',command=lambda:a.open_learning(recent=True)).pack(side='right')
        self.label(textcard,'原文与译文 · 双击英文单词查词 · 最近 40 段',fg='muted',size=9).grid(row=1,column=0,columnspan=2,sticky='w',pady=(4,14))
        a.history=tk.Text(textcard,wrap='word',height=8,width=20,font=('Microsoft YaHei UI',-19),bd=0,
                          padx=4,pady=4,spacing1=4,spacing3=10,selectbackground='#D6E5DD',exportselection=False,state='disabled')
        a.history.grid(row=2,column=0,sticky='nsew')
        self.colors.append((a.history,{'bg':'card','fg':'text','insertbackground':'text','selectbackground':'soft','selectforeground':'text'}))
        scroll=ttk.Scrollbar(textcard,command=a.history.yview);scroll.grid(row=2,column=1,sticky='ns');a.history.configure(yscrollcommand=scroll.set)
        a.history.bind('<Double-Button-1>',a.lookup_clicked)
        a.history.bind('<ButtonPress-1>',lambda e:setattr(a,'history_dragging',True))
        a.history.bind('<ButtonRelease-1>',lambda e:setattr(a,'history_dragging',False))
        bar=self.frame(textcard);bar.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(12,0))
        a.read_pause_button=ttk.Button(bar,text='暂停翻页',command=a.pause_reading);a.read_pause_button.pack(side='left')
        ttk.Button(bar,text='追到最新',command=a.latest_reading).pack(side='left',padx=6)
        ttk.Button(bar,text='查选中文字',command=a.lookup_selected).pack(side='right')
        replay=self.card(work);replay.grid(row=2,column=0,sticky='ew',pady=(14,0));replay.columnconfigure(0,weight=1)
        self.label(replay,'原声回听',size=12,bold=True).grid(row=0,column=0,sticky='w')
        a.clip_combo=ttk.Combobox(replay,state='readonly',values=[]);a.clip_combo.grid(row=1,column=0,columnspan=2,sticky='ew',pady=8)
        controls=self.frame(replay);controls.grid(row=2,column=0,columnspan=2,sticky='ew')
        ttk.Button(controls,text='播放片段',style='Accent.TButton',command=a.play_audio).pack(side='left')
        ttk.Button(controls,text='停止回听',command=a.stop_audio).pack(side='left',padx=7)
        ttk.Checkbutton(controls,text='循环播放',variable=a.audio_loop).pack(side='left')
        self.label(replay,textvariable=a.replay_status,fg='muted',size=9,wraplength=460,justify='left',anchor='w').grid(row=3,column=0,columnspan=2,sticky='ew',pady=(9,0))

        sound=self.scroll_page(self.pages['sound'])
        c=self.section(sound,'声音来源','录制所选耳机 / 扬声器的系统声音，不使用麦克风。')
        a.audio_combo=ttk.Combobox(c,state='readonly',values=['正在读取输出设备…']);a.audio_combo.current(0);a.audio_combo.pack(fill='x',pady=6)
        a.audio_combo.bind('<<ComboboxSelected>>',lambda e:a.input_changed())
        c=self.section(sound,'识别引擎','设备、模型与断句设置，在重新开始采集后生效。')
        for title,var,values in [('计算设备',a.speech_device,['GPU优先','仅CPU']),('语音模型',a.speech_model,list(speech_models)),('断句等待',a.pause_gap,['0.6 秒（较快断句）','1.2 秒（自然停顿）','1.8 秒（长停顿）'])]:
            self.combo(c,title,var,values,a.input_changed if var is not a.pause_gap else a.save)
        ttk.Checkbutton(c,text='疑难句最多复核一次',variable=a.speech_review,command=a.save).pack(anchor='w',pady=7)
        ttk.Checkbutton(c,text='静音 3 分钟释放模型（恢复时需要唤醒）',variable=a.idle_release,command=a.save).pack(anchor='w',pady=7)
        ttk.Button(c,text='1999 效果优先',command=a.quality_preset).pack(anchor='w',pady=8)
        c=self.section(sound,'角色与专名','提示辅助辨音；可以在采集中更新，不强制替换相近单词。')
        self.combo(c,'场景词库',a.speech_profile,list(profiles),a.apply_names)
        row=self.frame(c);row.pack(fill='x',pady=8)
        entry=ttk.Entry(row,textvariable=a.speech_hint);entry.pack(side='left',fill='x',expand=True);entry.bind('<Return>',lambda e:a.apply_names())
        ttk.Button(row,text='应用专名',command=a.apply_names).pack(side='left',padx=(8,0))
        c=self.section(sound,'可选模型','从本地扩展包安装，不调用付费接口。')
        self.label(c,textvariable=a.turbo_status,fg='muted',wraplength=580).pack(anchor='w',pady=6)
        a.install_model_button=ttk.Button(c,text='安装 turbo 扩展…',command=a.install_turbo);a.install_model_button.pack(anchor='w',pady=6)

        sub=self.scroll_page(self.pages['captions'])
        c=self.section(sub,'字幕位置','只读取画面和声音，窗口与游戏文件保持原样。')
        for value,label in [('A','A · 原文下方'),('B','B · 独立字幕条')]:
            ttk.Radiobutton(c,text=label,value=value,variable=a.layout,command=a.switch_layout).pack(anchor='w',pady=8)
        row=self.frame(c);row.pack(fill='x',pady=8)
        ttk.Button(row,text='框选原字幕 / OCR 区域',command=lambda:a.pick('roi')).pack(side='left')
        ttk.Button(row,text='设置 B 字幕区',command=lambda:a.pick('dock')).pack(side='left',padx=8)
        self.label(c,textvariable=a.region_label,fg='muted').pack(anchor='w',pady=4)
        self.label(c,textvariable=a.dock_label,fg='muted').pack(anchor='w',pady=4)
        ttk.Button(c,text='测试字幕位置',command=a.demo).pack(anchor='w',pady=8)
        c=self.section(sub,'长句与阅读','长句按页显示；暂停翻页时，识别仍继续。')
        ttk.Checkbutton(c,text='阅读保护：读完再换',variable=a.reading_protect,command=a.reading_changed).pack(anchor='w',pady=8)
        self.combo(c,'阅读速度',a.reading_pace,['正常阅读','慢速阅读'],a.reading_pace_changed)
        for title,var,lo,hi in [('字幕字号',a.size,18,40),('保留段数',a.keep_count,1,8),('最多行数',a.max_lines,1,12)]:
            row=self.frame(c);row.pack(fill='x',pady=8);self.label(row,title,width=12,anchor='w').pack(side='left')
            ttk.Spinbox(row,from_=lo,to=hi,textvariable=var,width=8,state='readonly',command=a.resize).pack(side='left')
        self.label(c,textvariable=a.visible_status,fg='muted',wraplength=560).pack(anchor='w',pady=10)
        c=self.section(sub,'快捷键','Alt + Shift 组合键')
        self.label(c,'T  切换 A/B        P  开始 / 停止        H  暂隐字幕\nR  暂停 / 继续翻页        L  追到最新        S  显示面板',fg='muted',justify='left').pack(anchor='w',pady=8)

        theme=self.scroll_page(self.pages['themes'])
        c=self.section(theme,'给学习换一种心情','主题立即生效，不会中断采集或清空文本。')
        for key,(name,mood) in THEMES.items():
            ttk.Radiobutton(c,text=name+'  ·  '+mood,value=key,variable=a.theme,command=a.change_theme).pack(anchor='w',pady=18)
        self.label(c,'两套静态配色，随心切换。\n外观切换不会打断正在进行的听读。',fg='muted',justify='left',wraplength=560).pack(anchor='w',pady=16)

        rail=self.frame(self.shell,'bg',width=304);rail.grid(row=0,column=2,sticky='ns',padx=(0,22),pady=24)
        rail.grid_propagate(False);rail.columnconfigure(0,weight=1);rail.rowconfigure(1,weight=1)
        art=self.card(rail);art.grid(row=0,column=0,sticky='ew',pady=(0,15))
        self.art_label=self.label(art,'LISTEN\nLEARN\nREMEMBER',size=22,bold=True,justify='left',anchor='w')
        self.art_label.pack(fill='x',pady=(6,12))
        self.theme_title=self.label(art,size=12,bold=True);self.theme_title.pack(anchor='w',pady=(8,2))
        self.theme_note=self.label(art,fg='muted',size=8);self.theme_note.pack(anchor='w')
        from embedded_dictionary import DictionaryPanel
        dictionary_card=self.card(rail);dictionary_card.grid(row=1,column=0,sticky='nsew')
        self.label(dictionary_card,'独立词典',size=14,bold=True).pack(anchor='w',pady=(0,13))
        a.dictionary_panel=DictionaryPanel(dictionary_card,a.add_name)
        a.dictionary_panel.frame.pack(fill='both',expand=True)
        self.apply_theme()
        self.show('work')

    def frame(self,parent,bg='card',**kwargs):
        w=tk.Frame(parent,**kwargs);self.colors.append((w,{'bg':bg}));return w

    def label(self,parent,text=None,bg='card',fg='text',size=10,bold=False,**kwargs):
        if text is not None:kwargs['text']=text
        w=tk.Label(parent,font=('Microsoft YaHei UI',-round(size*1.45),'bold' if bold else 'normal'),**kwargs)
        self.colors.append((w,{'bg':bg,'fg':fg}));return w

    def card(self,parent):
        w=self.frame(parent,padx=18,pady=16,highlightthickness=1)
        self.colors.append((w,{'highlightbackground':'border'}));return w

    def section(self,parent,title,description):
        c=self.card(parent);c.pack(fill='x',pady=(0,14))
        self.label(c,title,size=15,bold=True).pack(anchor='w')
        self.label(c,description,fg='muted',wraplength=550,justify='left',size=9).pack(anchor='w',pady=(5,13))
        return c

    def combo(self,parent,title,var,values,command):
        row=self.frame(parent);row.pack(fill='x',pady=8)
        self.label(row,title,width=12,anchor='w').pack(side='left')
        box=ttk.Combobox(row,textvariable=var,values=values,state='readonly',width=27)
        box.pack(side='left',fill='x',expand=True);box.bind('<<ComboboxSelected>>',lambda e:command())
        return box

    def scroll_page(self,page):
        canvas=tk.Canvas(page,highlightthickness=0);self.colors.append((canvas,{'bg':'bg'}))
        scrollbar=ttk.Scrollbar(page,command=canvas.yview);scrollbar.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True);canvas.configure(yscrollcommand=scrollbar.set)
        body=self.frame(canvas,'bg');item=canvas.create_window((0,0),window=body,anchor='nw')
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        def wheel(e):
            # Only scroll this visible page; Text/Combobox keep their own bindings.
            if str(e.widget).startswith(str(page)) and not isinstance(e.widget,(tk.Text,ttk.Combobox)):
                canvas.yview_scroll(-int(e.delta/120),'units')
        self.root.bind('<MouseWheel>',wheel,add='+')
        return body

    def show(self,key):
        self.current=key;self.pages[key].tkraise()
        self.title.configure(text={'work':'文本与回听','sound':'声音与识别','captions':'字幕与阅读','themes':'外观主题'}[key])
        p=self.palette
        for k,b in self.buttons.items():
            b.configure(bg=p['accent'] if key==k else p['nav'],fg='white',activebackground=p['accent'],activeforeground='white')

    def apply_theme(self):
        key=self.app.theme.get();self.palette=p=PALETTES.get(key,PALETTES['vertin'])
        self.root.configure(bg=p['bg'])
        for widget,attrs in self.colors:
            widget.configure(**{name:p.get(value,value) for name,value in attrs.items()})
        for name in ['TFrame','TLabel','TCheckbutton','TRadiobutton']:
            self.style.configure(name,background=p['card'],foreground=p['text'],font=('Microsoft YaHei UI',-15))
        self.style.configure('TButton',padding=(12,8),font=('Microsoft YaHei UI',-15),background=p['soft'],foreground=p['text'],borderwidth=0)
        self.style.map('TButton',background=[('active',p['border'])])
        self.style.configure('Accent.TButton',background=p['accent'],foreground='white')
        self.style.map('Accent.TButton',background=[('active',p['nav'])],foreground=[('disabled','#B9C2BC')])
        self.style.configure('TCombobox',padding=7,fieldbackground=p['card'],foreground=p['text'],arrowsize=15)
        self.style.map('TCombobox',fieldbackground=[('readonly',p['card'])],selectbackground=[('readonly',p['card'])],selectforeground=[('readonly',p['text'])])
        self.style.configure('TEntry',padding=7,fieldbackground=p['card'],foreground=p['text'])
        self.style.map('TCheckbutton',background=[('active',p['card'])]);self.style.map('TRadiobutton',background=[('active',p['card'])])
        self.art_label.configure(fg=p['accent'])
        name,mood=THEMES.get(key,THEMES['vertin']);self.theme_title.configure(text=name);self.theme_note.configure(text=mood)
        self.app.dictionary_panel.apply_theme(p)
        if self.app.dictionary is not None and not self.app.dictionary.closed:self.app.dictionary.apply_theme(p)
        self.show(self.current)
