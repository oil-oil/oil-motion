from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "image_job.py"
sys.path.insert(0, str(SCRIPT.parent))
import image_job

FAKE_KEY = "FAKE-ZENMUX-" + "0" * 16


def png_bytes(mode: str, corner_alpha: int = 0) -> bytes:
    if mode == "RGBA":
        image = Image.new("RGBA", (64, 64), (0, 0, 0, corner_alpha))
        for x in range(16, 48):
            for y in range(16, 48):
                image.putpixel((x, y), (200, 80, 40, 255))
    else:
        image = Image.new("RGB", (64, 64), (120, 160, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


class ImageJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def generate(self, image: bytes, background: str, references: list[Path] | None = None):
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            return FakeResponse({"data": [{"b64_json": base64.b64encode(image).decode("ascii")}]})

        output = self.root / "K0.png"
        with mock.patch.object(image_job, "require_api_key", return_value=FAKE_KEY), \
                mock.patch.object(image_job.urllib.request, "urlopen", side_effect=fake_urlopen), \
                contextlib.redirect_stdout(io.StringIO()):
            result = image_job.generate_image("测试", output, background=background, references=references)
        return result, requests

    def test_background_is_required_on_cli(self):
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "--prompt", "x", "--output", str(self.root / "a.png"), "--dry-run"],
            capture_output=True, text=True, env={**os.environ, "ZENMUX_API_KEY": ""},
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("--background", run.stderr)

    def test_dry_run_needs_no_key_and_routes_references_to_edits(self):
        reference = self.root / "ref.png"
        reference.write_bytes(png_bytes("RGB"))
        base = [sys.executable, str(SCRIPT), "--prompt", "x", "--output", str(self.root / "a.png"), "--background", "opaque", "--dry-run"]
        env = {key: value for key, value in os.environ.items() if key != "ZENMUX_API_KEY"}
        generations = json.loads(subprocess.run(base, capture_output=True, text=True, check=True, env=env).stdout)
        edits = json.loads(subprocess.run([*base, "--image", str(reference)], capture_output=True, text=True, check=True, env=env).stdout)
        self.assertTrue(generations["endpoint"].endswith("/images/generations"))
        self.assertTrue(edits["endpoint"].endswith("/images/edits"))
        self.assertEqual(edits["background"], "opaque")
        self.assertEqual(edits["references"], [str(reference.resolve())])

    def test_size_follows_model_constraints(self):
        self.assertEqual(image_job.parse_size("2048x1152", image_job.DEFAULT_IMAGE_MODEL), (2048, 1152))
        for bad in ("1000x1000", "4096x1024", "512x512", "wide"):
            with self.assertRaises(ValueError):
                image_job.parse_size(bad, image_job.DEFAULT_IMAGE_MODEL)

    def test_transparent_keyframe_with_real_alpha_is_accepted(self):
        result, requests = self.generate(png_bytes("RGBA", corner_alpha=0), "transparent")
        self.assertEqual(result.name, "K0.png")
        payload = json.loads(requests[0].data)
        self.assertEqual(payload["background"], "transparent")
        self.assertNotIn("transparent background", payload["prompt"])
        with Image.open(result) as saved:
            self.assertIn("A", saved.getbands())

    def test_transparent_request_without_real_alpha_is_rejected(self):
        for image in (png_bytes("RGB"), png_bytes("RGBA", corner_alpha=255)):
            for leftover in self.root.glob("K0*"):
                leftover.unlink()
            with self.assertRaises(RuntimeError) as raised:
                self.generate(image, "transparent")
            self.assertIn("透明验收失败", str(raised.exception))
            self.assertFalse((self.root / "K0.png").exists())
            self.assertTrue((self.root / "K0.rejected.png").exists())

    def test_opaque_scene_keyframe_skips_alpha_gate(self):
        result, requests = self.generate(png_bytes("RGB"), "opaque")
        self.assertEqual(result.name, "K0.png")
        self.assertEqual(json.loads(requests[0].data)["background"], "opaque")

    def test_references_use_multipart_edits(self):
        reference = self.root / "product.png"
        reference.write_bytes(png_bytes("RGB"))
        _, requests = self.generate(png_bytes("RGB"), "opaque", references=[reference])
        request = requests[0]
        self.assertTrue(request.full_url.endswith("/images/edits"))
        self.assertIn("multipart/form-data", request.get_header("Content-type"))
        self.assertIn(b'name="image[]"; filename="product.png"', request.data)

    def test_refuses_to_overwrite_existing_output(self):
        (self.root / "K0.png").write_bytes(b"keep")
        with mock.patch.object(image_job, "require_api_key", side_effect=AssertionError("不应读取密钥")):
            with self.assertRaises(FileExistsError):
                image_job.generate_image("测试", self.root / "K0.png", background="opaque")
        self.assertEqual((self.root / "K0.png").read_bytes(), b"keep")

    def test_http_error_does_not_echo_key(self):
        fake_key = FAKE_KEY
        error = urllib.error.HTTPError("https://zenmux.ai", 401, "denied", {}, io.BytesIO(f"bad key {fake_key}".encode()))
        self.addCleanup(error.close)
        with mock.patch.object(image_job, "require_api_key", return_value=fake_key), \
                mock.patch.object(image_job.urllib.request, "urlopen", side_effect=error), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError) as raised:
                image_job.generate_image("测试", self.root / "K0.png", background="opaque")
        self.assertNotIn(fake_key, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
