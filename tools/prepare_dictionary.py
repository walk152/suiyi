"""Build the offline dictionary from a verified ECDICT CSV; network is setup only."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from download_models import reject_links

BLOB = 'c4ade63ea08cf39d9c3475e96929036d64d94c94'
SOURCE_URL = 'https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv'
EXPECTED_BYTES = 65933428


def verify_csv(path, expected_blob=BLOB):
    path=Path(path)
    digest=hashlib.sha1(b'blob '+str(path.stat().st_size).encode()+b'\0')
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=expected_blob:
        raise ValueError('ECDICT Git blob mismatch; do not accept changed upstream data without review')


def prepare_source(path):
    path=Path(path);reject_links(path)
    if path.exists():
        verify_csv(path)
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        request=urllib.request.Request(SOURCE_URL,headers={'User-Agent':'Suiyi-dictionary-setup/0.5'})
        with urllib.request.urlopen(request,timeout=60) as response:
            if not response.geturl().startswith('https://'):raise ValueError('HTTPS redirect required')
            with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.part',delete=False) as stream:
                temporary=Path(stream.name);size=0
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>EXPECTED_BYTES:raise ValueError('Dictionary source exceeds locked size')
                    stream.write(chunk)
        verify_csv(temporary)
        temporary.replace(path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def build(source,target,expected_blob=BLOB):
    source,target=Path(source),Path(target)
    verify_csv(source,expected_blob)
    reject_links(target)
    if target.exists():raise FileExistsError('Dictionary already exists; refusing to overwrite it')
    target.parent.mkdir(parents=True,exist_ok=True)
    handle,temporary_name=tempfile.mkstemp(dir=target.parent,suffix='.sqlite3.part')
    os.close(handle);temporary=Path(temporary_name)
    db=None
    try:
        db=sqlite3.connect(temporary)
        db.execute('CREATE TABLE entries (word TEXT PRIMARY KEY, data BLOB NOT NULL) WITHOUT ROWID')
        db.execute('CREATE TABLE forms (form TEXT, lemma TEXT, PRIMARY KEY(form,lemma)) WITHOUT ROWID')
        fields=['word','phonetic','translation','definition','pos','exchange','tag']
        with source.open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                word=row['word'].strip().casefold()
                if not word or len(word)>128:continue
                data={field:row.get(field,'') for field in fields}
                db.execute('INSERT OR REPLACE INTO entries VALUES (?,?)',
                           (word,zlib.compress(json.dumps(data,ensure_ascii=False).encode(),9)))
                for item in row.get('exchange','').split('/'):
                    if ':' not in item:continue
                    kind,value=item.split(':',1)
                    for form in value.split(','):
                        form=form.strip().casefold()
                        if not form or len(form)>128 or form==word:continue
                        if kind=='0':pair=(word,form)
                        elif kind in ('p','d','i','3','r','t','s'):pair=(form,word)
                        else:continue
                        db.execute('INSERT OR IGNORE INTO forms VALUES (?,?)',pair)
        db.commit()
        count=db.execute('SELECT count(*) FROM entries').fetchone()[0]
        if not count:raise ValueError('Dictionary contains no entries')
        db.execute('VACUUM');db.close();db=None
        reject_links(target)
        # Windows rename refuses an existing destination, preserving concurrent work.
        temporary.rename(target)
        return count
    finally:
        if db is not None:db.close()
        temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',type=Path,help='Use existing verified ECDICT CSV without network')
    parser.add_argument('--output',type=Path,default=ROOT/'dictionary/ecdict.sqlite3')
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Dictionary already exists; no files changed. Remove only a known damaged database before rebuilding.')
    source=args.csv or ROOT/'.cache/ecdict.csv'
    if args.csv is None:prepare_source(source)
    count=build(source,args.output)
    print(f'Built {count} entries: {args.output.name}')


if __name__=='__main__':main()
