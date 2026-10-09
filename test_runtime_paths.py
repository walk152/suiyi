import errno,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import runtime_paths

class PreferenceTests(unittest.TestCase):
    def test_redirected_profile_cross_device_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            data={'layout':'B','size':27,'speech_model':'small.en'}
            with patch.object(runtime_paths,'DATA_ROOT',Path(directory)),patch.object(Path,'replace',side_effect=OSError(errno.EXDEV,'redirected profile')):
                runtime_paths.write_settings(data)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),data)
            self.assertFalse(path.with_suffix('.tmp').exists())

    def test_permission_error_keeps_previous_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json';path.write_text('{"layout":"B"}',encoding='utf-8')
            with patch.object(runtime_paths,'DATA_ROOT',Path(directory)),patch.object(Path,'replace',side_effect=PermissionError('read-only')):
                with self.assertRaises(PermissionError):runtime_paths.write_settings({'layout':'A'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')),{'layout':'B'})

if __name__=='__main__':unittest.main()
