"""Keep installed resources separate from per-user writable preferences."""
from pathlib import Path
import os
import sys
import errno
import json

FROZEN = bool(getattr(sys, 'frozen', False))
APP_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, '_MEIPASS', APP_ROOT))
DATA_ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData'/'Local')))/'Suiyi' if FROZEN else APP_ROOT

def settings_path():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return DATA_ROOT/'settings.json'

def write_settings(data):
    atomic_text(settings_path(),json.dumps(data,ensure_ascii=False,indent=2))

def atomic_text(target,content):
    target=Path(target)
    temp=target.with_suffix('.tmp')
    temp.write_text(content,encoding='utf-8')
    try:
        temp.replace(target)
    except OSError as exc:
        # Some redirected/encrypted Windows profile folders reject replace as EXDEV,
        # even when both names are in one directory. Preserve usable preferences there.
        if exc.errno!=errno.EXDEV and getattr(exc,'winerror',None)!=17:
            raise
        target.write_text(content,encoding='utf-8')
        try:temp.unlink(missing_ok=True)
        except OSError:pass
