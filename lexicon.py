"""On-demand, bounded-memory offline dictionary lookups. No network fallback."""
from pathlib import Path
from contextlib import closing
import json, re, sqlite3, zlib
from runtime_paths import BUNDLE_ROOT

WORD=re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")

def word_at(text, offset):
    for match in WORD.finditer(text):
        if match.start() <= offset < match.end():return match.group()
    return ''

def normalize(query):
    return ' '.join(query.strip().replace('’',"'").split()).strip('.,!?;:\"“”()[]').casefold()

def lookup(query, path=None):
    query=normalize(query)
    if not query or len(query)>128 or len(query.split())>6:
        return {'query':query,'entries':[],'suggestions':[],'message':'请输入一个英文单词或短语（最多 6 个词）。'}
    path=Path(path) if path else BUNDLE_ROOT/'dictionary/ecdict.sqlite3'
    if not path.is_file():raise FileNotFoundError('离线词库尚未准备。源码版请运行 python tools/prepare_dictionary.py；安装版请重新安装完整包。')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA cache_size=-1024');db.execute('PRAGMA mmap_size=0')
        def entry(word):
            row=db.execute('SELECT data FROM entries WHERE word=?',(word,)).fetchone()
            return json.loads(zlib.decompress(row[0])) if row else None
        found=[]
        exact=entry(query)
        if exact:found.append(exact)
        for (lemma,) in db.execute('SELECT lemma FROM forms WHERE form=? LIMIT 4',(query,)):
            result=entry(lemma)
            if result and result not in found:found.append(result)
        suggestions=[]
        if not found:
            prefix=query[:max(2,len(query)-2)]
            suggestions=[r[0] for r in db.execute('SELECT word FROM entries WHERE word>=? AND word<? LIMIT 8',(prefix,prefix+'\uffff'))]
        return {'query':query,'entries':found,'suggestions':suggestions,
                'message':'' if found else '本地词典未收录此词。人名、游戏专名可加入“专名提示”，不会自动编造释义。'}

def format_result(result):
    parts=[]
    for item in result['entries']:
        lines=[item['word']+('  /'+item['phonetic']+'/' if item.get('phonetic') else '')]
        if item.get('translation'):lines.append(item['translation'].replace('\\n','\n'))
        if item.get('definition'):lines.append('英文释义：\n'+item['definition'].replace('\\n','\n'))
        if item.get('exchange'):lines.append('词形：'+item['exchange'])
        parts.append('\n\n'.join(lines))
    if result.get('message'):parts.append(result['message'])
    if result['suggestions']:parts.append('相近词条：'+', '.join(result['suggestions']))
    return '\n\n────────────\n\n'.join(parts)
