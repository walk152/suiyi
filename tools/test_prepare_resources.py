"""Small synthetic resource checks: no network, real recordings or large models."""
from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import download_models as models
import prepare_dictionary as dictionary
from lexicon import lookup


def row(content):return {'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}


class ResourceTests(unittest.TestCase):
    def test_corrupt_download_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'weights.bin';p.write_bytes(b'original')
            with self.assertRaises(ValueError):models.atomic_stream(io.BytesIO(b'bad'),p,row(b'new'))
            self.assertEqual(p.read_bytes(),b'original')
            self.assertEqual(list(Path(folder).glob('*.part')),[])

    def test_cache_requires_hash_and_does_not_use_network_when_correct(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'weights.bin';p.write_bytes(b'bad')
            self.assertFalse(models.verify_file(p,row(b'new')))
            calls=[]
            def opener(*args,**kwargs):calls.append(1);return io.BytesIO(b'new')
            self.assertTrue(models.download_verified('https://example.invalid/model',p,row(b'new'),opener))
            self.assertFalse(models.download_verified('https://example.invalid/model',p,row(b'new'),opener))
            self.assertEqual(calls,[1])

    def test_archive_escape_and_unknown_member_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.zip'
            for name in ['../outside.bin','unknown.bin','C:/outside.bin']:
                with zipfile.ZipFile(p,'w') as z:z.writestr(name,b'good')
                with self.assertRaises(ValueError):models.extract_verified(p,Path(folder)/'out',{'expected.bin':row(b'good')})
            self.assertFalse((Path(folder)/'outside.bin').exists())

    def test_turbo_inline_metadata_matches_existing_manifest(self):
        import base64
        lock=models.load_lock(ROOT/'models-lock.json')['models']['whisper-turbo']
        manifest=json.loads((ROOT/'turbo_manifest.json').read_text())['files']
        for relative,expected in lock['files'].items():
            original=manifest['models/whisper-turbo/'+relative]
            self.assertEqual((expected['bytes'],expected['sha256']),(original['bytes'],original['sha256']))
        metadata=lock['files']['source.json']
        self.assertEqual(row(base64.b64decode(metadata['inline_base64'])),
                         {key:metadata[key] for key in ('bytes','sha256')})

    def test_default_model_selection_skips_turbo(self):
        with tempfile.TemporaryDirectory() as folder:
            lock={'models':{'whisper-turbo':{'optional':True}}}
            self.assertEqual(models.prepare_models(lock,Path(folder)/'models',Path(folder)/'cache'),{})

    def test_dictionary_build_hash_and_inflection(self):
        raw=b'word,phonetic,translation,definition,pos,exchange,tag\ngo,,move,,,p:went,\nrain,,water,,,,\n'
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'sample.csv';p.write_bytes(raw)
            output=Path(folder)/'dictionary.sqlite3'
            with self.assertRaises(ValueError):dictionary.build(p,output,expected_blob='0'*40)
            self.assertFalse(output.exists())
            self.assertEqual(dictionary.build(p,output,expected_blob=blob),2)
            self.assertEqual(lookup('went',path=output)['entries'][0]['word'],'go')
            self.assertEqual(lookup('rain',path=output)['entries'][0]['translation'],'water')
            with self.assertRaises(FileExistsError):dictionary.build(p,output,expected_blob=blob)


if __name__=='__main__':unittest.main()
