import hashlib
from pathlib import Path
import tempfile
import unittest
from build_turbo_addon import build


class BuildTests(unittest.TestCase):
    def test_local_build_reuse_and_corruption_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);name='models/whisper-turbo/config.json'
            source=root/name;source.parent.mkdir(parents=True);source.write_bytes(b'fixture')
            expected={name:dict(bytes=7,sha256=hashlib.sha256(b'fixture').hexdigest())}
            output=root/'test.suiyimodel'
            self.assertTrue(build(root,output,expected))
            self.assertFalse(build(root,output,expected))
            output.write_bytes(b'keep damaged user file')
            with self.assertRaises(Exception):build(root,output,expected)
            self.assertEqual(output.read_bytes(),b'keep damaged user file')

    def test_invalid_source_creates_no_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);name='models/whisper-turbo/config.json'
            source=root/name;source.parent.mkdir(parents=True);source.write_bytes(b'bad')
            output=root/'test.suiyimodel'
            with self.assertRaises(AssertionError):build(root,output,{name:dict(bytes=3,sha256='bad')})
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
