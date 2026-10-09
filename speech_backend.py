"""Local Whisper loading, explicit GPU selection and CPU fallback."""
from pathlib import Path
import os, sys
import numpy as np
from public_audio import install_faster_whisper_audio
install_faster_whisper_audio()
from runtime_paths import APP_ROOT, BUNDLE_ROOT, FROZEN
from dataclasses import dataclass
import re, time

DLL_HANDLES = []

def prepare_gpu():
    # Only the application's own Python environment; no game installation searches.
    package_root = BUNDLE_ROOT/'nvidia' if FROZEN else Path(sys.prefix)/'Lib'/'site-packages'/'nvidia'
    paths = [p for p in package_root.glob('*/bin') if p.is_dir()]
    for p in paths:
        DLL_HANDLES.append(os.add_dll_directory(str(p)))
    if paths:
        os.environ['PATH'] = os.pathsep.join(map(str,paths))+os.pathsep+os.environ.get('PATH','')

def load_recognizer(cfg, emit):
    from faster_whisper import WhisperModel
    language = cfg.get('language','en')
    choice = cfg.get('speech_model','small.en')
    name = 'turbo' if choice=='turbo' else ('small.en' if choice=='small.en' and language=='en' else 'base')
    path = str(APP_ROOT/'models'/('whisper-'+name))
    if name=='turbo':
        from model_pack import turbo_ready
        if not turbo_ready():raise FileNotFoundError('turbo 尚未安装，请在面板点击“安装 turbo 扩展…”导入离线扩展包。')
    if not Path(path,'model.bin').is_file():
        raise FileNotFoundError('缺少所选语音模型；源码版请运行 python download_models.py，安装版请重新安装完整离线包。')
    device = 'cuda' if cfg.get('speech_device','cuda') == 'cuda' else 'cpu'
    emit('status',f'正在加载 {name} / {"GPU" if device=="cuda" else "CPU"}，并预热…')
    try:
        if device == 'cuda':
            prepare_gpu()
        model = WhisperModel(path, device=device, compute_type='int8_float16' if device=='cuda' else 'int8',
                             cpu_threads=4, num_workers=1, local_files_only=True)
        # Force DLL/encoder initialization before starting audio capture.
        segments,_ = model.transcribe(np.zeros(16000,dtype=np.float32),language=language,
                                      beam_size=1,temperature=0,condition_on_previous_text=False)
        list(segments)
    except RuntimeError as exc:
        if device != 'cuda':
            raise
        emit('warning',f'GPU 不可用，已回退 CPU（速度可能降低）：{exc}')
        device='cpu'
        model=WhisperModel(path,device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    return model, device, name

def normalize_hint(hint):
    names=[]
    for name in re.split(r'[,，;；\n]+',hint):
        name=' '.join(name.split())[:60]
        if name and name.casefold() not in [x.casefold() for x in names]:names.append(name)
    return ', '.join(names[:20])[:500]

def prepare_audio(audio):
    audio=np.nan_to_num(np.asarray(audio,dtype=np.float32),nan=0.0,posinf=0.0,neginf=0.0)
    peak=float(np.max(np.abs(audio),initial=0))
    rms=float(np.sqrt(np.mean(audio*audio))) if len(audio) else 0
    if peak>1e-4 and 0<rms<.025:
        return audio*min(4.0,.025/rms,.95/peak)
    return audio

@dataclass
class Recognition:
    text: str
    uncertain: bool=False
    score: float=-10.0
    retried: bool=False
    review_skipped: bool=False

def recognize_detailed(model, job, language='en', hint='', review=True, learning=None, can_review=None):
    audio=prepare_audio(job.audio)
    if np.max(np.abs(audio),initial=0)<1e-5:return Recognition('')
    hint=normalize_hint(learning.hint(hint) if learning else hint)
    def decode(beam, words=hint):
        segments,_ = model.transcribe(audio, language=language, task='transcribe',
            beam_size=beam, temperature=0,
            vad_filter=False, condition_on_previous_text=False,
            hotwords=words or None, no_speech_threshold=.6,
            compression_ratio_threshold=2.4, log_prob_threshold=-1.0,
            max_new_tokens=128, hallucination_silence_threshold=None)
        valid=[s for s in segments if s.avg_logprob>-1.4 and s.no_speech_prob<.8 and s.compression_ratio<2.4]
        if not valid:return Recognition('')
        text=' '.join(s.text.strip() for s in valid).strip()
        score=sum(s.avg_logprob*max(1,len(s.text)) for s in valid)/sum(max(1,len(s.text)) for s in valid)
        return Recognition(text,score<-.75 or any(s.no_speech_prob>.5 for s in valid),score)
    result=decode(5 if job.final else 1)
    # One bounded retry for difficult final sentences, never a periodic GPU keep-alive.
    candidates=learning.candidates(result.text) if learning and job.final and review else []
    if job.final and review and (not result.text or result.uncertain or candidates):
        # Do not multiply latency when another utterance is already waiting.
        if can_review is not None and not can_review():
            result.review_skipped=True
            return result
        retry_hint=hint
        if candidates:
            from learning import bounded_names, split_names
            retry_hint=bounded_names(candidates+split_names(hint))
        second=decode(8,retry_hint)
        if second.text and second.score>result.score:result=second
        result.retried=True
    return result

def recognize(model, job, language='en', hint=''):
    return recognize_detailed(model,job,language,hint).text
