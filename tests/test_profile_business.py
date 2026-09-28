import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import oil_motion_config as config


class BusinessCredentialTests(unittest.TestCase):
    def test_profile_environment_reaches_business_reader(self):
        with patch.dict(os.environ, {'ZENMUX_API_KEY': 'TEST_KEY'}, clear=True), patch.object(Path, 'read_text', side_effect=AssertionError('不应读取旧凭据文件')):
            self.assertEqual(config.require_api_key(), 'TEST_KEY')

    def test_missing_key_points_to_page_and_run_entry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'OIL_MOTION_CONFIG_FILE': str(Path(tmp) / 'config.json')}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                config.require_api_key()
        message = str(raised.exception)
        self.assertIn('profile.ts', message)
        self.assertIn('run default', message)
        self.assertNotIn('oil_motion_config.py set', message)


if __name__ == '__main__':
    unittest.main()
