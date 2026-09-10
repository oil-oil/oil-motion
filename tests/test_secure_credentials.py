"""系统后端替身测试；不读取或写入真实凭据。"""
import io
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout, redirect_stderr

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'scripts'
if not SCRIPTS.exists(): SCRIPTS = ROOT / 'see/scripts'
sys.path.insert(0, str(SCRIPTS))
import secure_credentials as store

class CredentialTests(unittest.TestCase):
    def test_save_read_delete_only_use_backend(self):
        values = {}
        backend = MagicMock()
        backend.get_password.side_effect = lambda service, ref: values.get(ref)
        backend.set_password.side_effect = lambda service, ref, secret: values.update({ref:secret})
        backend.delete_password.side_effect = lambda service, ref: values.pop(ref)
        output = io.StringIO()
        with patch.object(store, 'backend', return_value=backend), redirect_stdout(output), redirect_stderr(output):
            store.save('test/reference', 'fake-credential-for-tests')
            self.assertEqual(store.read('test/reference'), 'fake-credential-for-tests')
            store.delete('test/reference')
        self.assertEqual(values, {})
        self.assertNotIn('fake-credential-for-tests', output.getvalue())

    def test_backend_failure_never_echoes_secret(self):
        backend = MagicMock()
        backend.set_password.side_effect = RuntimeError('fake-credential-for-tests')
        with patch.object(store, 'backend', return_value=backend):
            with self.assertRaises(RuntimeError) as error:
                store.save('test/reference', 'fake-credential-for-tests')
            self.assertNotIn('fake-credential-for-tests', str(error.exception))

    def test_unavailable_system_backend_does_not_select_plaintext(self):
        with patch.object(store.importlib, 'import_module', side_effect=ImportError), self.assertRaises(RuntimeError):
            store.backend()

if __name__ == '__main__': unittest.main()
