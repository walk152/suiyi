"""Offline runtime checks with an opt-in legacy device-capture compatibility path."""
import json
import multiprocessing as mp
from pathlib import Path
import time
import traceback
import os
from runtime_paths import APP_ROOT, BUNDLE_ROOT, DATA_ROOT

def check_runtime(output, capture_loopback=True):
    report={'root':str(APP_ROOT),'checks':{},'ok':False}
    try:
        from engine import offline, Translator, make_ocr, read_ocr
        offline()
        import socket
        try:
            socket.create_connection(('127.0.0.1',9),timeout=.1)
        except PermissionError:
            report['checks']['network_blocked']=True
        else:
            raise AssertionError('Network audit did not block connect')
        from PIL import Image, ImageDraw, ImageFont
        import os
        fixture=Image.new('RGB',(850,100),'white')
        ImageDraw.Draw(fixture).text((15,20),'We should leave before the rain starts.',fill='black',
             font=ImageFont.truetype(os.path.join(os.environ['WINDIR'],'Fonts','arial.ttf'),30))
        ocr=make_ocr()
        text=read_ocr(ocr,fixture)
        assert 'leave before the rain starts' in text.lower(),text
        report['checks']['ocr']=text
        from ocr_english import MODEL_NAME,MODEL_SHA256,MODEL_BYTES
        import hashlib
        english_model=BUNDLE_ROOT/'ocr_models'/MODEL_NAME
        assert english_model.stat().st_size==MODEL_BYTES
        assert hashlib.sha256(english_model.read_bytes()).hexdigest()==MODEL_SHA256
        report['checks']['english_ocr_model_verified']=True
        for direction,sentence in [('en_zh','We should leave before the rain starts.'),('zh_en','我们应该在下雨前离开。')]:
            translation=Translator(direction).translate(sentence)
            assert translation
            report['checks'][direction]=translation
        import soundcard as sc
        speakers=sc.all_speakers()
        report['checks']['audio_devices']=len(speakers)
        if capture_loopback:
            speaker=sc.default_speaker()
            with sc.get_microphone(speaker.id,include_loopback=True).recorder(samplerate=16000) as recorder:
                frames=recorder.record(numframes=None)
                assert frames.shape[0]>0
                report['checks']['loopback_shape']=list(frames.shape)
        else:
            # Listing output devices is read-only. Never open a microphone or
            # loopback recorder when validating a package with this mode.
            report['checks']['loopback_not_captured']=True
        import numpy as np
        from speech_stream import StreamingVad, AudioJob
        report['checks']['vad']=StreamingVad()(np.zeros(1024,dtype=np.float32))
        from lexicon import lookup
        assert lookup('rain')['entries'][0]['translation']
        assert any(e['word'].lower()=='go' for e in lookup('went')['entries'])
        report['checks']['offline_dictionary']=True
        import tempfile
        from learning import LearningStore,LearningSession,catalog
        with tempfile.TemporaryDirectory() as folder:
            store=LearningStore(Path(folder)/'memory.sqlite3')
            store.remember('1999','en','sentence','Hello Sinetto','Hello Sonetto')
            session=LearningSession('1999','en',store)
            assert session.correct('Hello Sinetto.')[0]=='Hello Sonetto'
            assert 'Kakania' in session.candidates('Cockania')
            report['checks']['learning_memory']=True
            report['checks']['built_in_names']=len(catalog())
        from faster_whisper.audio import decode_audio
        from speech_backend import load_recognizer,recognize
        sample=os.environ.get('SUIYI_TEST_AUDIO')
        preference=os.environ.get('SUIYI_TEST_DEVICE','cpu')
        if preference not in ('cpu','cuda','auto'):
            raise ValueError('SUIYI_TEST_DEVICE must be cpu, cuda or auto')
        if not sample:
            report['checks']['speech']={'skipped':True,'reason':'Set SUIYI_TEST_AUDIO to a permitted English speech sample for ASR checks.'}
        audio=decode_audio(sample,sampling_rate=16000) if sample else None
        device='cpu' if preference=='cpu' else 'cuda'
        for choice in ('small.en','turbo','base') if sample else ():
            from model_pack import turbo_ready
            if choice=='turbo' and not turbo_ready():
                report['checks']['turbo']={'optional':True,'installed':False};continue
            model,actual,name=load_recognizer({'speech_model':choice,'speech_device':device,'language':'en'},lambda *a:None)
            if preference!='auto':assert actual==device,(choice,actual)
            result=recognize(model,AudioJob(1,1,audio,True,time.monotonic()))
            assert len(result.split())>=5,result
            report['checks'][choice]={'device':actual,'text':result}
            if actual=='cuda':
                from public_checks import loaded_module_paths
                from runtime_paths import FROZEN
                nvidia=[path for path in loaded_module_paths() if path.name.lower().startswith(('cublas','cudnn','nvrtc'))]
                if FROZEN:assert nvidia and all(path.resolve().is_relative_to((BUNDLE_ROOT/'nvidia').resolve()) for path in nvidia),nvidia
                report['checks'][choice]['nvidia_libraries']=[path.name for path in nvidia]
            if choice=='small.en':
                model.model.unload_model(to_cpu=False)
                started=time.monotonic();model.model.load_model()
                report['checks']['wake_load_seconds']=time.monotonic()-started
                again=recognize(model,AudioJob(2,1,audio,True,time.monotonic()))
                assert again==result,(result,again)
                report['checks']['wake_transcription_preserved']=True
            del model
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

def main(output=None, capture_loopback=True):
    output=Path(output).resolve() if output is not None else DATA_ROOT/'installed-self-test.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    process=mp.Process(target=check_runtime,args=(output,capture_loopback))
    process.start()
    process.join(180)
    if process.is_alive():
        process.terminate();process.join()
        output.write_text(json.dumps({'ok':False,'error':'Self-test timeout'}),encoding='utf-8')
    if process.exitcode or not output.exists() or not json.loads(output.read_text(encoding='utf-8')).get('ok'):
        raise SystemExit(1)
