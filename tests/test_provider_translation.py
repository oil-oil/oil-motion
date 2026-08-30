from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VIDEO = load("video_job")
CONFIG = load("oil_motion_config")


def make_png(size: int = 8) -> bytes:
    # Minimal valid PNG (solid color) for base64 data-URI payload tests.
    import struct
    import zlib

    def chunk(tag: str, data: bytes) -> bytes:
        c = tag + data
        return (
            struct.pack(">I", len(data))
            + c
            + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes((80, 60, 40)) * size for _ in range(size))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class OrcaRouterPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.first = Path("/tmp/oil-test-first.png")
        cls.last = Path("/tmp/oil-test-last.png")
        cls.first.write_bytes(make_png())
        cls.last.write_bytes(make_png())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.first.unlink(missing_ok=True)
        cls.last.unlink(missing_ok=True)

    def arguments(self, **overrides: object) -> Namespace:
        values: dict[str, object] = {
            "provider": "orcarouter",
            "prompt": "test motion",
            "prompt_file": None,
            "first_frame": None,
            "last_frame": None,
            "loop_frame": False,
            "reference_image": [],
            "model": "minimax/minimax-h3",
            "resolution": "768p",
            "ratio": None,
            "duration": None,
            "seed": None,
            "frames": None,
        }
        values.update(overrides)
        return Namespace(**values)

    def test_orcarouter_payload_uses_openai_style_fields(self) -> None:
        payload = VIDEO.build_payload(self.arguments(duration=5))

        self.assertEqual(payload["model"], "minimax/minimax-h3")
        self.assertEqual(payload["prompt"], "test motion")
        self.assertEqual(payload["duration"], 5)
        self.assertEqual(payload["size"], "768p")
        self.assertNotIn("content", payload)
        self.assertNotIn("resolution", payload)

    def test_orcarouter_payload_embeds_first_and_last_frames_in_metadata(
        self,
    ) -> None:
        payload = VIDEO.build_payload(
            self.arguments(
                first_frame=str(self.first),
                last_frame=str(self.last),
                ratio="1:1",
            )
        )

        metadata = payload["metadata"]
        self.assertEqual(metadata["ratio"], "1:1")
        self.assertTrue(metadata["first_frame_image"].startswith("data:image/png;base64,"))
        self.assertTrue(metadata["last_frame_image"].startswith("data:image/png;base64,"))
        self.assertNotIn("content", payload)

    def test_orcarouter_reference_images_use_images_field(self) -> None:
        payload = VIDEO.build_payload(
            self.arguments(reference_image=[str(self.first)])
        )

        self.assertEqual(len(payload["images"]), 1)
        self.assertTrue(payload["images"][0].startswith("data:image/png;base64,"))

    def test_orcarouter_loop_frame_pins_same_image_to_both_frames(self) -> None:
        payload = VIDEO.build_payload(
            self.arguments(
                first_frame=str(self.first),
                loop_frame=True,
            )
        )

        self.assertEqual(
            payload["metadata"]["first_frame_image"],
            payload["metadata"]["last_frame_image"],
        )


class ZenMuxPayloadRegressionTests(unittest.TestCase):
    def test_zenmux_payload_keeps_content_parts_and_resolution(self) -> None:
        args = Namespace(
            provider="zenmux",
            prompt="test motion",
            prompt_file=None,
            first_frame=None,
            last_frame=None,
            loop_frame=False,
            reference_image=[],
            model="minimax/minimax-h3",
            resolution="768p",
            ratio=None,
            duration=5,
            seed=None,
            frames=None,
        )
        payload = VIDEO.build_payload(args)

        self.assertEqual(payload["model"], "minimax/minimax-h3")
        self.assertEqual(payload["content"][0]["text"], "test motion")
        self.assertEqual(payload["resolution"], "768p")
        self.assertEqual(payload["generate_audio"], False)
        self.assertNotIn("size", payload)


class ProviderResponseTests(unittest.TestCase):
    def test_orcarouter_url_prefers_metadata_url(self) -> None:
        response = {
            "id": "task_1",
            "status": "completed",
            "metadata": {"url": "https://cdn.example.com/output.mp4"},
        }
        url = VIDEO.walk_for_url(
            response, VIDEO.preferred_url_keys("orcarouter")
        )
        self.assertEqual(url, "https://cdn.example.com/output.mp4")

    def test_zenmux_url_prefers_video_url(self) -> None:
        response = {"video_url": "https://zenmux.example.com/v.mp4", "url": "other"}
        url = VIDEO.walk_for_url(response, VIDEO.preferred_url_keys("zenmux"))
        self.assertEqual(url, "https://zenmux.example.com/v.mp4")

    def test_status_terminal_sets_are_provider_aware(self) -> None:
        self.assertTrue(VIDEO.status_is_terminal("completed", "orcarouter"))
        self.assertTrue(VIDEO.status_is_terminal("succeeded", "zenmux"))
        self.assertFalse(VIDEO.status_is_terminal("in_progress", "orcarouter"))
        self.assertFalse(VIDEO.status_is_terminal("queued", "zenmux"))


class ConfigProviderTests(unittest.TestCase):
    def test_config_env_names_differ_by_provider(self) -> None:
        self.assertEqual(CONFIG.provider_api_key_env("zenmux"), "ZENMUX_API_KEY")
        self.assertEqual(
            CONFIG.provider_api_key_env("orcarouter"), "ORCAROUTER_API_KEY"
        )
        self.assertEqual(CONFIG.provider_config_section("zenmux"), "zenmux")
        self.assertEqual(
            CONFIG.provider_config_section("orcarouter"), "orcarouter"
        )


class GenerateProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "out.mp4"
        self.metadata = self.root / "meta.json"
        self.first = self.root / "first.png"
        self.first.write_bytes(make_png(256))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_generate_orcarouter_completed_path_writes_video_and_metadata(
        self,
    ) -> None:
        import shutil
        from unittest import mock

        args = Namespace(
            provider="orcarouter",
            prompt="test motion",
            prompt_file=None,
            first_frame=str(self.first),
            last_frame=None,
            loop_frame=True,
            reference_image=[],
            model="minimax/minimax-h3",
            resolution="768p",
            ratio="1:1",
            duration=4,
            seed=None,
            frames=None,
            stage="pilot",
            segment_index=1,
            pilot_approval=None,
            continuity_mode=None,
            previous_tail=None,
            frame_chain_manifest=None,
            output=str(self.video),
            last_frame_output=str(self.root / "tail.jpg"),
            metadata=str(self.metadata),
            poll_interval=0.01,
            timeout=30.0,
            force=False,
        )

        completed = {
            "id": "task_1",
            "status": "completed",
            "metadata": {"url": "https://cdn.example.com/output.mp4"},
        }

        def fake_request(method: str, url: str, api_key: str, payload=None) -> dict:
            if method == "POST":
                return {"id": "task_1", "status": "queued"}
            return completed

        def fake_download(url: str, target: Path) -> None:
            target.write_bytes(b"fake-mp4")

        with (
            mock.patch.object(VIDEO, "request_json", side_effect=fake_request),
            mock.patch.object(VIDEO, "download", side_effect=fake_download),
            mock.patch.object(
                VIDEO,
                "extract_last_frame",
                side_effect=lambda src, dst: dst.write_bytes(b"tail"),
            ),
            mock.patch.object(VIDEO, "require_api_key", return_value="key"),
        ):
            VIDEO.generate(args)

        self.assertTrue(self.video.is_file())
        self.assertTrue(self.metadata.is_file())
        payload = json.loads(self.metadata.read_text(encoding="utf-8"))
        self.assertEqual(payload["lastFrame"]["source"], "video-fallback")
        self.assertEqual(payload["payload"]["size"], "768p")
        self.assertEqual(
            payload["payload"]["metadata"]["first_frame_image"],
            "<local-image-data-uri>",
        )

    def test_legacy_namespace_without_provider_falls_back_to_zenmux(self) -> None:
        args = Namespace(
            prompt="test motion",
            prompt_file=None,
            first_frame=None,
            last_frame=None,
            loop_frame=False,
            reference_image=[],
            model="minimax/minimax-h3",
            resolution="768p",
            ratio=None,
            duration=5,
            seed=None,
            frames=None,
        )
        payload = VIDEO.build_payload(args)

        self.assertIn("content", payload)
        self.assertNotIn("size", payload)


if __name__ == "__main__":
    unittest.main()
