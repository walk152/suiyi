"""Bounded subtitle reading pages; capture and ASR continue independently."""
from collections import OrderedDict, deque
import difflib, re, time
from core import fit_lines

def reading_seconds(text, pace=1.0):
    units=len(re.findall(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*",text))+len(re.findall(r'[\u3400-\u9fff]',text))*.6
    return min(40.0,max(3.0,1.0+units/3.0))*pace

def map_offset(old, new, offset):
    """Keep an unread boundary through ASR edits; a replacement is reread, never skipped."""
    if offset<=0:return 0
    for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if a<=offset<b:return c+offset-a if tag=='equal' else c
        if offset==a:return c
    return len(new)

class ReadingPager:
    def __init__(self,limit=40):
        self.limit=limit;self.reset()

    def reset(self):
        self.pending=OrderedDict();self.done=deque(maxlen=160)
        self.active=None;self.offset=0;self.end=0
        self.started=None;self.deadline=0;self.content='';self.page_number=1
        self.lines=[];self.colors=[];self.paused=False;self.paused_at=None
        self.current_lines=[];self.current_colors=[];self.jump_tail=False
        self.suspended=False;self.wrap_key=None;self.wrap_value=None
        self.pending_edit=False
        self.previous=deque(maxlen=7);self.skipped=0

    def push(self, record):
        ident=record['id']
        if ident in self.done:return
        old=self.pending.get(ident)
        if old and record.get('revision',1)<old.get('revision',1):return
        if old and ident==self.active:
            for tag,a,b,c,d in difflib.SequenceMatcher(None,old['text'],record['text'],autojunk=False).get_opcodes():
                if tag!='equal' and a<self.end and b>=self.offset:self.pending_edit=True
            self.offset=map_offset(old['text'],record['text'],self.offset)
            self.end=map_offset(old['text'],record['text'],self.end)
        self.pending[ident]=dict(record)
        while len(self.pending)>self.limit:
            victim=next((key for key in self.pending if key!=self.active),None)
            if victim is None:break
            self.pending.pop(victim);self.done.append(victim);self.skipped+=1

    def discard(self, ident):
        self.pending.pop(ident,None)
        if ident==self.active:self.active=None;self.started=None;self.content=''

    def suspend(self):
        self.suspended=True

    def _wrap(self,text,width,measure):
        key=(text,width)
        if key!=self.wrap_key:
            self.wrap_key=key;self.wrap_value=fit_lines(text,width,measure)
        return self.wrap_value

    def pause(self, now=None):
        now=time.monotonic() if now is None else now
        if self.paused:
            self.deadline+=now-self.paused_at
            if self.started is not None:self.started+=now-self.paused_at
            self.paused=False;self.paused_at=None
        else:self.paused=True;self.paused_at=now
        return self.paused

    def latest(self):
        if not self.pending:return
        ident=next(reversed(self.pending))
        for old in list(self.pending):
            if old!=ident:self.done.append(old);self.pending.pop(old)
        self.active=None;self.offset=0;self.end=0;self.started=None;self.content=''
        self.previous.clear();self.paused=False;self.paused_at=None;self.skipped=0
        self.jump_tail=True

    def _finish(self):
        if self.current_lines:self.previous.append((list(self.current_lines),list(self.current_colors)))
        self.pending.pop(self.active,None);self.done.append(self.active)
        self.active=None;self.offset=0;self.started=None;self.content='';self.page_number=1

    def view(self, width, capacity, measure, pace=1.0, keep=3, now=None):
        now=time.monotonic() if now is None else now
        capacity=max(1,capacity)
        if self.paused:return self.lines,self.colors,self.status()
        if self.suspended:self.started=None;self.suspended=False
        if not self.pending:self.lines=[];self.colors=[];return [],[],self.status()
        if self.active not in self.pending:
            self.active=next(iter(self.pending));self.offset=0;self.started=None;self.content='';self.page_number=1
        record=self.pending[self.active];text=record['text']
        usable=max(1,width-measure('› '))
        if self.jump_tail:
            wrapped=self._wrap(text,usable,measure);pos=0;starts=[]
            for line in wrapped:
                found=text.find(line,pos);starts.append(max(0,found));pos=max(pos,found+len(line))
            self.offset=starts[max(0,len(starts)-capacity)];self.jump_tail=False
        # Only advance after the displayed content has had its reading time.
        if self.started is not None and now>=self.deadline and not self.pending_edit:
            if self.end<len(text):
                self.offset=self.end;self.started=None;self.content='';self.page_number+=1
            elif len(self.pending)>1:
                self._finish();return self.view(width,capacity,measure,pace,keep,now)
            elif record.get('final',True) and now>=self.deadline+20:
                self._finish();self.lines=[];self.colors=[];return [],[],self.status()
        wrapped=self._wrap(text[self.offset:],usable,measure)[:capacity]
        end=self.offset
        for line in wrapped:
            found=text.find(line,end)
            if found>=0:end=found+len(line)
        while end<len(text) and text[end].isspace():end+=1
        self.end=end
        content='\n'.join(wrapped)
        if self.started is None:
            self.started=now;self.deadline=now+reading_seconds(content,pace)
        elif content!=self.content:
            # New words receive a short extension; identical streaming revisions do not.
            self.deadline=max(self.deadline,self.started+reading_seconds(content,pace),now+min(2.5,reading_seconds(content,pace)))
        self.content=content
        self.pending_edit=False
        color='#f0c87a' if record.get('uncertain') else ('#eef6e6' if record.get('final',True) else '#b9d7ed')
        current=['› '+wrapped[0]]+wrapped[1:] if wrapped else []
        colors=[color]*len(current)
        self.current_lines=current;self.current_colors=colors
        spare=capacity-len(current)
        history=[]
        if spare and keep>1:
            for lines,_ in list(self.previous)[-(keep-1):]:history+=lines
            history=history[-spare:]
        self.lines=history+current;self.colors=['#a3b5a0']*len(history)+colors
        return self.lines,self.colors,self.status()

    def status(self):
        return dict(paused=self.paused,pending=max(0,len(self.pending)-1),page=self.page_number,skipped=self.skipped)

def self_test():
    """Packaged module verification with synthetic text, no UI/capture/user data."""
    reader=ReadingPager()
    reader.push(dict(id='a',text='one two three four five six',final=True))
    first=reader.view(13,1,len,now=0)[0]
    assert first==['› one two']
    reader.push(dict(id='b',text='next',final=True))
    assert reader.view(13,1,len,now=1)[0]==first
    assert reader.view(13,1,len,now=4)[0]==['› three four']
    reader.pause(now=5);assert reader.view(13,1,len,now=60)[0]==['› three four']
    reader.latest();assert reader.view(13,1,len,now=61)[0]==['› next']
    from speech_stream import Segmenter
    assert Segmenter().silence_limit==1.2
    return dict(ok=True,version='0.4.1',paging=True,paused_reading=True,latest=True,pause_seconds=1.2)
