import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import oil_motion_config as config
class ConfigTests(unittest.TestCase):
    def test_main_replaces_legacy_secret_with_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';path.write_text(json.dumps({'zenmux':{'api_key':'old-fake','model':'keep'}}))
            with patch.dict(os.environ,{'OIL_MOTION_CONFIG_FILE':str(path)}),patch.object(sys,'argv',['config','set']),patch.object(config.getpass,'getpass',return_value='new-fake'),patch.object(config.secure_credentials,'save') as save,redirect_stdout(io.StringIO()):
                self.assertEqual(config.main(),0)
            save.assert_called_once_with(config.CREDENTIAL_REF,'new-fake')
            data=json.loads(path.read_text());self.assertEqual(data['zenmux']['model'],'keep')
            self.assertEqual(data['zenmux']['credential_ref'],config.CREDENTIAL_REF)
            self.assertNotIn('fake',path.read_text())
    def test_store_failure_keeps_original_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';path.write_text('{"zenmux":{"model":"keep"}}')
            before=path.read_text()
            with patch.object(config.getpass,'getpass',return_value='new-fake'),patch.object(config.secure_credentials,'save',side_effect=RuntimeError('unavailable')),self.assertRaises(RuntimeError):
                config.set_api_key(path)
            self.assertEqual(path.read_text(),before)
if __name__ == '__main__':unittest.main()
