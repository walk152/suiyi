"""Local inference in a disposable child process; no online fallbacks."""
from pathlib import Path
import os, sys, re, time, queue, threading

from runtime_paths import APP_ROOT
ROOT = APP_ROOT

def offline():
    os.chdir(ROOT)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1')
    def audit(event, args):
        if event == 'socket.connect':
            raise PermissionError('随译运行模式禁止网络连接')
    sys.addaudithook(audit)

class Translator:
    def __init__(self, direction, threads=4):
        import ctranslate2, sentencepiece
        self.direction = direction
        folder = ROOT / 'models' / f'translate-{direction}-1_9'
        if not (folder / 'model' / 'model.bin').exists():
            raise FileNotFoundError('缺少本地翻译模型；源码版请运行 python download_models.py，安装版请重新安装完整离线包。')
        self.tokens = sentencepiece.SentencePieceProcessor(model_proto=(folder / 'sentencepiece.model').read_bytes())
        self.model = ctranslate2.Translator(os.path.relpath(folder/'model'), device='cpu', compute_type='int8',
                                           inter_threads=1, intra_threads=threads)
        self.cache = {}

    def translate(self, text):
        text = text.strip()
        if not text:
            return ''
        if text in self.cache:
            return self.cache[text]
        # Translate complete source sentences together. No claims of LLM-style discourse reasoning.
        from translation_text import token_batches
        batches = token_batches(text, self.tokens)
        # Bound each request without dropping long paragraphs at the decoder
        # limit. OCR line wraps have already been rejoined into source sentences.
        result = self.model.translate_batch(batches, beam_size=4, max_decoding_length=512,
                                            repetition_penalty=1.05, max_batch_size=8)
        joiner = '' if self.direction == 'en_zh' else ' '
        output = joiner.join(self.tokens.decode(r.hypotheses[0]).replace('\u2581', ' ') for r in result).strip()
        if self.direction == 'en_zh':
            output = re.sub(r'\s+([，。！？；：])', r'\1', output)
        if not output:
            raise RuntimeError('本地模型没有返回译文，请尝试较短的完整句子。')
        if len(self.cache) >= 100:
            self.cache.pop(next(iter(self.cache)))
        self.cache[text] = output
        return output

def make_ocr():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1, text_score=0.55,
                    det_use_cuda=False, rec_use_cuda=False, cls_use_cuda=False)

def read_ocr(ocr, image):
    from screen_text import read_blocks
    return '\n'.join(block['text'] for block in read_blocks(ocr, image, None))

def actual_roi(cfg):
    from screen_capture import actual_region
    return actual_region(cfg)

def capture_screen(cfg, stopped, emit, translator, controls=None):
    from screen_capture import capture_screen as run_screen
    return run_screen(cfg, stopped, emit, translator, controls)

def capture_audio(cfg, stopped, emit, translator, controls=None):
    import numpy as np
    import soundcard as sc
    from speech_stream import StreamingVad, Segmenter, PendingAudio, AudioFramer, trim_overlap
    from speech_backend import load_recognizer, recognize_detailed, prepare_audio
    from learning import LearningSession
    from audio_review import ReplayGate, make_audio_clip
    learning=LearningSession(cfg.get('speech_profile','general'),cfg.get('language','en'))
    model, device, model_name = load_recognizer(cfg, emit)
    pending = PendingAudio(capacity=3, max_age=3.0)
    replay_gate = ReplayGate()
    voice=threading.Event()
    activity={'last_voice':time.monotonic()}
    def reader():
        # WASAPI mono capture is unreliable; capture native channels and average afterwards.
        try:
            vad = StreamingVad()
            segmenter = Segmenter(preview_after=.8 if device=='cuda' else 1.5,
                                  silence=cfg.get('speech_pause',1.2),
                                  preview_every=.85 if device=='cuda' else 1.5)
            framer=AudioFramer()
            speaker = sc.get_speaker(cfg['speaker_id'])
            mic = sc.get_microphone(speaker.id, include_loopback=True)
            def reset_stream():
                nonlocal segmenter, framer
                emit('discard',f'audio-{segmenter.ident}')
                ident=segmenter.ident+1
                segmenter=Segmenter(preview_after=.8 if device=='cuda' else 1.5,
                                    silence=cfg.get('speech_pause',1.2),
                                    preview_every=.85 if device=='cuda' else 1.5)
                segmenter.ident=ident
                framer=AudioFramer()
                vad.reset();pending.clear();voice.clear()
            with mic.recorder(samplerate=16000, blocksize=2048) as recorder:
                while not stopped.is_set():
                    # Consume available data without accumulating a fixed-frame silence backlog.
                    samples=recorder.record(numframes=None).mean(axis=1).astype('float32')
                    now=time.monotonic()
                    suppressed,reset,generation=replay_gate.reader_state(now)
                    if reset:
                        reset_stream()
                        replay_gate.reader_ack(generation)
                    if suppressed:
                        # Drain the device while replaying, without invoking VAD/ASR.
                        if not len(samples):stopped.wait(.02)
                        continue
                    if not len(samples):
                        stopped.wait(.02);continue
                    frames,reset=framer.push(samples,now)
                    if reset:
                        emit('discard',f'audio-{segmenter.ident}')
                        ident=segmenter.ident+1
                        segmenter=Segmenter(preview_after=.8 if device=='cuda' else 1.5,
                                            silence=cfg.get('speech_pause',1.2),
                                            preview_every=.85 if device=='cuda' else 1.5)
                        segmenter.ident=ident;vad.reset();pending.clear()
                        emit('status','音频时钟中断后已恢复，旧缓冲已清理，正在监听当前声音。')
                    for i,chunk in enumerate(frames):
                        if replay_gate.active():break
                        probability=vad(prepare_audio(chunk))
                        if probability>=.5:
                            activity['last_voice']=now;voice.set()
                        ended=now-(len(frames)-1-i)*.064
                        for job in segmenter.push(chunk,probability,now=ended):pending.put(job)
        except Exception as exc:
            emit('error', f'音频采集失败：{exc}')
            stopped.set()
    threading.Thread(target=reader, daemon=True).start()
    emit('status', f'{model_name} / {device.upper()} 就绪：边说边出草稿，停顿后定稿；系统混音。')
    recent = ''
    draft_ident=None;draft_names=[]
    recent_at=0.0
    loaded=True
    idle_reported=False
    resumed=False
    def wake():
        nonlocal loaded,idle_reported,resumed
        if not loaded:
            emit('status','检测到说话，正在按需唤醒模型；音频采集继续保留当前短句。')
            model.model.load_model()
            if translator:translator.model.load_model()
            loaded=True
            resumed=True
        idle_reported=False
    while not stopped.is_set():
        if controls is not None:
            while True:
                try:update=controls.get_nowait()
                except queue.Empty:break
                if 'replay_hold' in update:
                    replay_gate.request(update['replay_hold'],update.get('request_id'))
                    pending.clear();voice.clear()
                    recent='';recent_at=0.;draft_names=[];draft_ident=None
                    activity['last_voice']=time.monotonic()
                    if update['replay_hold']:
                        emit('status','正在准备回听，暂时暂停新声音识别。')
                    else:
                        emit('status','回听已结束，正在恢复声音识别。')
                if any(key in update for key in ('speech_hint','speech_profile','reload_memory')):
                    cfg['speech_hint']=str(update.get('speech_hint',cfg.get('speech_hint','')))[:500]
                    profile=update.get('speech_profile',learning.profile)
                    if profile!=learning.profile:learning=LearningSession(profile,cfg.get('language','en'))
                    elif update.get('reload_memory'):learning.reload()
                    draft_names=[]
                    emit('status','专名与学习记忆已应用，下一段识别生效。')
        if replay_gate.active():
            ready=replay_gate.take_ready()
            if ready is not None:emit('replay_ready',ready)
            stopped.wait(.025)
            continue
        if voice.is_set():
            voice.clear();wake()
        try:
            job = pending.get(timeout=.25,max_age=8.0 if resumed else None)
        except queue.Empty:
            silent=time.monotonic()-activity['last_voice']
            idle_limit=cfg.get('idle_release_seconds',180)
            if loaded and idle_limit>0 and silent>=idle_limit:
                model.model.unload_model(to_cpu=False)
                if translator:translator.model.unload_model(to_cpu=False)
                loaded=False
                emit('status','已静音 3 分钟：模型已卸载，保留轻量声音检测；说话时自动唤醒。')
            elif loaded and silent>=10 and not idle_reported:
                idle_reported=True
                emit('status','等待声音：不运行转写；'+('持续静音 3 分钟后自动释放模型。' if idle_limit else '保留当前模型以快速恢复。'))
            continue
        wake()
        resumed=False
        dropped = pending.drop_count()
        if dropped:
            emit('warning', f'识别曾积压，已跳过 {dropped} 段过时任务，优先跟上当前语音。')
        start = time.monotonic()
        from learning import bounded_names, split_names
        if job.ident!=draft_ident:draft_ident=job.ident;draft_names=[]
        hint=bounded_names(split_names(cfg.get('speech_hint',''))+draft_names)
        result = recognize_detailed(model,job,cfg.get('language','en'),hint,
                                    review=cfg.get('speech_review',True),learning=learning,
                                    can_review=lambda: not pending.has_other(job.ident) and time.monotonic()-job.ended<1.2)
        text=result.text
        if not job.final:
            # Next scheduled revision can use suspected names without an extra decode.
            draft_names=list(dict.fromkeys(learning.candidates(text)+draft_names))[:3]
        if time.monotonic()-recent_at>15:recent=''
        text = trim_overlap(recent, text, job.continuation)
        raw_text=text
        text,learned=learning.correct(text) if job.final and text else (text,False)
        if text and not stopped.is_set():
            output = translator.translate(text) if translator else text
            caption=dict(source=text, text=output, cost=time.monotonic()-start,
                         lag=time.monotonic()-job.ended, kind='音频',
                         id=f'audio-{job.ident}', revision=job.revision, final=job.final,
                         uncertain=result.uncertain,retried=result.retried,
                         learned=learned,raw_source=raw_text,review_skipped=result.review_skipped)
            if job.final and cfg.get('audio_review',False):
                caption['audio_clip']=make_audio_clip(job.audio,job.continuation)
            emit('caption',caption)
            if job.final:
                learning.observe(text,not result.uncertain or learned)
                recent = raw_text;recent_at=time.monotonic()
        elif job.final:
            emit('discard', f'audio-{job.ident}')

def run(cfg, stopped, events, controls=None):
    offline()
    def emit(kind, payload):
        try:
            events.put((kind, payload), timeout=.1)
        except queue.Full:
            pass
    try:
        import native
        native.dpi_aware()
        direction = cfg.get('direction')
        translator = Translator(direction) if direction else None
        if cfg['input'] == 'screen':
            capture_screen(cfg, stopped, emit, translator, controls)
        elif cfg['input'] == 'text':
            out = translator.translate(cfg['text']) if translator else cfg['text']
            emit('caption', dict(source=cfg['text'], text=out, cost=0, kind='手动文字'))
        else:
            capture_audio(cfg, stopped, emit, translator, controls)
    except Exception as exc:
        emit('error', f'{type(exc).__name__}: {exc}')
    finally:
        emit('finished', '')
