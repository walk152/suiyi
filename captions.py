"""Keep multiple utterances; a streaming revision replaces only its own utterance."""
from collections import OrderedDict
import time
from core import fit_lines

class CaptionHistory:
    def __init__(self, limit=40):
        self.records = OrderedDict()
        self.counter = 0
        self.limit = limit

    def clear(self):
        self.records.clear()

    def update(self, data, now=None):
        now = time.monotonic() if now is None else now
        ident = data.get('id')
        if ident is None:
            self.counter += 1
            ident = f'local-{self.counter}'
        old = self.records.get(ident)
        revision = data.get('revision', 1)
        if old and (revision < old['revision'] or (old['final'] and not data.get('final', True))):
            return False
        self.records[ident] = dict(data, id=ident, revision=revision, final=data.get('final', True), updated=now)
        while len(self.records) > self.limit:
            self.records.popitem(last=False)
        return True

    def recent(self, count, seconds=35, now=None):
        now = time.monotonic() if now is None else now
        return [r for r in self.records.values() if now-r['updated'] <= seconds][-count:]

def visible_lines(records, width, capacity, measure):
    """Newest lines stay visible. Complete paragraphs remain in the scrollable history."""
    lines, colors = [], []
    for record in records:
        text = record['text'] + (' …' if not record['final'] else '') + (' [?]' if record.get('uncertain') else '')
        wrapped = fit_lines('› '+text, width, measure)
        color = '#f0c87a' if record.get('uncertain') else ('#b9d7ed' if not record['final'] else '#eef6e6')
        lines.extend(wrapped)
        colors.extend([color]*len(wrapped))
    return lines[-capacity:], colors[-capacity:], len(lines)
