import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from model_pack import install_pack,turbo_ready,IDENTITY,PREFIX

class ModelPackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data={PREFIX+'model.bin':b'model weights',PREFIX+'config.json':b'{}'}
        self.expected={n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in self.data.items()}
        self.package=self.root/'test.suiyimodel'
    def tearDown(self):self.temp.cleanup()
    def pack(self,rows=None):
        with zipfile.ZipFile(self.package,'w') as z:
            for n,b in (self.data if rows is None else rows).items():z.writestr(n,b)
    def test_install_registers_addon_and_reinstall_keeps_existing(self):
        self.pack();manifest=self.root/'suiyi-install-manifest.txt';manifest.write_text(IDENTITY+'\nSuiyi.exe\n')
        self.assertFalse(turbo_ready(self.root,self.expected))
        self.assertTrue(install_pack(self.package,root=self.root,expected=self.expected))
        self.assertTrue(turbo_ready(self.root,self.expected))
        self.assertIn('models\\whisper-turbo\\model.bin',manifest.read_text())
        self.assertFalse(install_pack(self.package,root=self.root,expected=self.expected))
        self.assertIn('Suiyi.exe',manifest.read_text())
    def test_corruption_rejected_before_model_commit(self):
        rows=dict(self.data);rows[PREFIX+'model.bin']=b'wrong weights';self.pack(rows)
        with self.assertRaises(ValueError):install_pack(self.package,root=self.root,expected=self.expected)
        self.assertFalse((self.root/'models/whisper-turbo').exists())
    def test_traversal_and_extra_file_rejected(self):
        rows=dict(self.data);rows['../outside']=b'no';self.pack(rows)
        with self.assertRaises(ValueError):install_pack(self.package,root=self.root,expected=self.expected)
        self.assertFalse((self.root/'models').exists())
    def test_duplicate_entries_rejected(self):
        self.pack()
        with zipfile.ZipFile(self.package,'a') as z:z.writestr(PREFIX+'config.json',b'{}')
        with self.assertRaises(ValueError):install_pack(self.package,root=self.root,expected=self.expected)
    def test_missing_file_rejected(self):
        self.pack({PREFIX+'model.bin':self.data[PREFIX+'model.bin']})
        with self.assertRaises(ValueError):install_pack(self.package,root=self.root,expected=self.expected)

if __name__=='__main__':unittest.main()
