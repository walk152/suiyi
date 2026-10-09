"""Small, inspectable local memory. No network, weight training, or guessed corrections."""
import json, re, sqlite3, time, difflib
from pathlib import Path
from contextlib import closing
from functools import lru_cache
from runtime_paths import BUNDLE_ROOT, DATA_ROOT

PROFILES = {'通用': 'general', '重返未来：1999': '1999'}

def normalized(text):
    return ' '.join(re.findall(r"\w+(?:['’-]\w+)*", text.casefold()))

@lru_cache(maxsize=1)
def catalog():
    return json.loads((BUNDLE_ROOT/'names1999.json').read_text(encoding='utf-8'))['names']

def split_names(text):
    return [x.strip() for x in re.split('[,，;；\n]', text) if x.strip()]

def sound_key(text):
    # Candidate retrieval only; never use a phonetic key to replace transcript text.
    s=re.sub('[^a-z]','',text.casefold())
    s=s.replace('ph','f').replace('ck','k').replace('c','k').replace('q','k')
    s=s.translate(str.maketrans({'d':'t','z':'s','b':'p','v':'f'}))
    s=re.sub('[aeiouyhw]','',s)
    return re.sub(r'(.)\1+',r'\1',s)

def bounded_names(names, limit=16):
    seen=set(); result=[]
    for name in names:
        name=' '.join(str(name).split())[:60]
        if name and name.casefold() not in seen:
            if len(', '.join(result+[name]))>400:break
            seen.add(name.casefold());result.append(name)
            if len(result)>=limit:break
    return ', '.join(result)

class LearningStore:
    def __init__(self, path=None):
        self.path=Path(path) if path else DATA_ROOT/'learning.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS memory (profile TEXT, language TEXT, kind TEXT, source TEXT, target TEXT, updated REAL, PRIMARY KEY(profile,language,kind,source))')

    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        db.execute('PRAGMA cache_size=-256')
        db.execute('PRAGMA journal_size_limit=0')
        return db

    def rows(self, profile, language='en'):
        with closing(self.connect()) as db:
            return [dict(kind=a,source=b,target=c,updated=d) for a,b,c,d in db.execute(
                'SELECT kind,source,target,updated FROM memory WHERE profile=? AND language=? ORDER BY updated DESC LIMIT 1000',(profile,language))]

    def remember(self, profile, language, kind, source, target):
        source=source.strip();target=target.strip()
        if kind not in ('sentence','name'):raise ValueError('未知记忆类型')
        if not target or len(target)>800:raise ValueError('请填写正确内容，最多 800 字符。')
        if kind=='sentence' and (not normalized(source) or len(source)>800):raise ValueError('请填写原识别句，最多 800 字符。')
        if kind=='name':
            if len(target)>60 or len(target.split())>6:raise ValueError('专名请控制在 6 个词、60 字符以内。')
            source=target.casefold()
        else:source=normalized(source)
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO memory VALUES (?,?,?,?,?,?)',(profile,language,kind,source,target,time.time()))
            db.execute('DELETE FROM memory WHERE rowid NOT IN (SELECT rowid FROM memory ORDER BY updated DESC LIMIT 1000)')

    def forget(self, profile, language, row):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM memory WHERE profile=? AND language=? AND kind=? AND source=?',(profile,language,row['kind'],row['source']))

class LearningSession:
    def __init__(self, profile='general', language='en', store=None):
        self.profile=profile;self.language=language;self.store=store or LearningStore()
        self.recent=[];self.reload()

    def reload(self):
        rows=self.store.rows(self.profile,self.language)
        self.names=[x['target'] for x in rows if x['kind']=='name']
        self.corrections={x['source']:x['target'] for x in rows if x['kind']=='sentence'}
        if self.profile=='1999' and self.language=='en':
            known={normalized(x['en']):x['en'] for x in catalog()}
            for source,target in self.corrections.items():
                old=source.split();new=normalized(target).split()
                for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
                    corrected=' '.join(new[c:d])
                    if tag!='equal' and corrected in known and known[corrected] not in self.names:
                        self.names.append(known[corrected])

    def hint(self, manual=''):
        return bounded_names(split_names(manual)+self.recent[:4]+self.names[:6])

    def candidates(self, text):
        if self.profile!='1999' or self.language!='en':return []
        words=re.findall(r"[\w’'-]+",text)
        windows=[' '.join(words[i:i+n]).casefold() for i in range(len(words)) for n in (1,2,3) if i+n<=len(words)]
        ranked=[]
        for row in catalog():
            name=row['en'];key=name.casefold()
            # Ordinary nouns / very short names require an explicit user hint.
            if not row.get('auto',True) or len(key)<5:continue
            if key in windows:continue
            scores=[]
            for w in windows:
                if len(w)<5 or abs(len(key)-len(w))>3:continue
                ratio=difflib.SequenceMatcher(None,key,w,autojunk=False).ratio()
                phonetic=len(sound_key(key))>=2 and sound_key(key)==sound_key(w) and ratio>=.6
                if ratio>=.78 or phonetic:scores.append(ratio)
            if scores:ranked.append((max(scores),name))
        return [name for _,name in sorted(ranked,reverse=True)[:3]]

    def correct(self, text):
        fixed=self.corrections.get(normalized(text))
        return (fixed,True) if fixed else (text,False)

    def observe(self, text, certain=True):
        if not certain or self.profile!='1999' or self.language!='en':return
        for row in catalog():
            name=row['en']
            if row.get('auto',True) and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text,re.I):
                self.recent=[name]+[x for x in self.recent if x!=name]
        self.recent=self.recent[:6]
