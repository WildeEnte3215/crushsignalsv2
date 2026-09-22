import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from src.config import Settings
from src.utils import Cache, ProductionError, atomic
from src.voice import Voice
from src.sfx import SFX
from src.demo import fixture_plan
from src.schemas import Research, Verdict
from src.pipeline import produce
from tests.test_engine import alignment

ROOT = Path(__file__).resolve().parents[1]


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.s = Settings(ROOT)
        self.cache = Cache(self.root / "cache")

    def test_tts_wire_and_cached_audio(self):
        http, budget = Mock(), Mock()
        http.request.return_value = {
            "audio_base64": base64.b64encode(b"test-audio").decode(),
            "alignment": alignment("hello"),
        }
        voice = Voice(self.s, http, self.cache, budget)
        with patch(
            "src.voice.valid_media", side_effect=lambda p, kind: Path(p).is_file()
        ):
            first = voice.generate("hello", ["voice-id"])
            second = voice.generate("hello", ["voice-id"])
        self.assertEqual(first, second)
        self.assertEqual(http.request.call_count, 1)
        call = http.request.call_args
        self.assertIn("/v1/text-to-speech/voice-id/with-timestamps?", call.args[1])
        self.assertEqual(call.args[3]["model_id"], "eleven_multilingual_v2")
        self.assertNotIn("language_code", call.args[3])

    def test_sfx_endpoint_and_no_silent_setup_fallback(self):
        http = Mock()
        http.request.side_effect = ProductionError("Permission denied")
        sfx = SFX(self.s, http, self.cache, Mock())
        with self.assertRaises(ProductionError):
            sfx.generate("whoosh", live_required=True)
        call = http.request.call_args
        self.assertIn("/v1/sound-generation", call.args[1])
        self.assertEqual(call.args[3]["model_id"], "eleven_text_to_sound_v2")
        path, origin = sfx.generate("whoosh")
        self.assertTrue(path.is_file())
        self.assertIn("procedural", origin)

    def test_scene_failure_resumes_completed_scene_checkpoints(self):
        self.s.root = self.root
        self.s.video["max_diagram_fraction"] = 1
        self.s.prompt = lambda name: "fixture prompt"
        plan = fixture_plan()
        evidence = Research(
            summary="fixture",
            sources=[
                {"url": "https://example.com/a", "title": "A", "primary": True},
                {"url": "https://example.org/b", "title": "B", "primary": False},
            ],
            claims=[
                {"id": "a", "statement": "A", "source_urls": ["https://example.com/a"]},
                {"id": "b", "statement": "B", "source_urls": ["https://example.org/b"]},
            ],
            uncertainties=[],
        )
        run = {"id": "resume-test", "topic": "fixture", "created": "2026-09-14"}
        audio = self.root / "audio.mp3"
        audio.write_bytes(b"fixture")
        fake_voice = Mock()
        fake_voice.subscription.return_value = {"tier": "starter"}
        fake_voice.select.return_value = ["voice"]
        fake_voice.generate.return_value = (
            audio,
            {"alignment": {}, "voice_id": "voice"},
        )
        fake_timing = {"duration": 40, "scenes": [], "words": [], "shots": []}
        called = []
        fail = [True]

        def select(scene, folder):
            called.append(scene.id)
            if scene.id == plan.scenes[2].id and fail[0]:
                fail[0] = False
                raise ProductionError("Injected scene failure")
            return {"kind": "diagram"}

        ranker = Mock()
        ranker.select.side_effect = select

        def render(*args):
            target = args[-1] / "candidate.mp4"
            atomic(target, b"fixture")
            return target

        with (
            patch(
                "src.pipeline.clients",
                return_value=(
                    Mock(),
                    self.cache,
                    Mock(summary=Mock(return_value={})),
                    Mock(),
                ),
            ),
            patch("src.pipeline.Voice", return_value=fake_voice),
            patch("src.pipeline.research", return_value=evidence) as researched,
            patch("src.pipeline.generate", return_value=plan) as generated,
            patch(
                "src.pipeline.fact_check",
                return_value=Verdict(
                    passed=True, checked_scene_ids=[], issues=[], evidence_urls=[]
                ),
            ),
            patch("src.pipeline.probe", return_value={"format": {"duration": "40"}}),
            patch("src.pipeline.timeline", return_value=fake_timing),
            patch("src.pipeline.Ranker", return_value=ranker),
            patch("src.pipeline.SFX") as sfx,
            patch("src.pipeline.render", side_effect=render),
            patch("src.pipeline.check"),
        ):
            sfx.return_value.schedule.return_value = []
            with self.assertRaises(ProductionError):
                produce(self.s, run)
            final = produce(self.s, run)
            self.assertTrue(final.is_file())
            self.assertEqual(researched.call_count, 1)
            self.assertEqual(generated.call_count, 1)
        self.assertEqual(called.count(plan.scenes[0].id), 1)
        self.assertEqual(called.count(plan.scenes[1].id), 1)
        self.assertEqual(called.count(plan.scenes[2].id), 2)
