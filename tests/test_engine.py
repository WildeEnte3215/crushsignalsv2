import ast
import base64
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from src.config import Settings
from src.utils import Cache, ProductionError
from src.http import Http, APIError
from src.budget import Budget, BudgetError
from src.openai_client import OpenAI
from src.schemas import Topic, Plan, Assessment
from src.voice import validate_alignment, Voice
from src.scene_planner import narration, timeline
from src.demo import fixture_plan
from src.stock.pexels import PexelsProvider
from src.stock.fallback import PixabayProvider
from src.subtitles import safe, subtitle_events
from src.render import crop_filter

ROOT = Path(__file__).resolve().parents[1]


def response(text):
    return {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ],
    }


def alignment(text):
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * 0.06 for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * 0.06 for i in range(len(text))],
    }


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.s = Settings(ROOT)
        self.cache = Cache(self.path)

    def ai(self, values):
        http = Mock()
        http.request.side_effect = values
        return OpenAI(self.s, http, self.cache, Mock()), http

    def test_python39_syntax_all_sources(self):
        for path in ROOT.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path), feature_version=(3, 9))

    def test_schema_objects_strict(self):
        def visit(x):
            if isinstance(x, dict):
                if x.get("type") == "object":
                    self.assertFalse(x["additionalProperties"])
                    self.assertEqual(set(x["required"]), set(x["properties"]))
                for v in x.values():
                    visit(v)
            elif isinstance(x, list):
                for v in x:
                    visit(v)

        for cls in [Plan, Topic, Assessment]:
            visit(cls.model_json_schema())

    def test_cache_corruption_and_ttl(self):
        self.cache.put("n", "key", {"ok": True})
        self.assertTrue(self.cache.get("n", "key")["ok"])
        self.assertIsNone(self.cache.get("n", "key", ttl=-1))
        self.cache.path("n", "key").write_text("broken")
        self.assertIsNone(self.cache.get("n", "key"))

    def test_401_no_retry_redaction(self):
        h = Http(["secret-value"])
        h.opener = Mock()
        h.opener.open.side_effect = urllib.error.HTTPError(
            "https://example.com", 401, "bad", {}, io.BytesIO(b"secret-value invalid")
        )
        with self.assertRaises(APIError) as e:
            h.request("GET", "https://example.com")
        self.assertNotIn("secret-value", str(e.exception))
        self.assertEqual(h.opener.open.call_count, 1)

    def test_retry_503_reserves_each_attempt(self):
        h = Http()
        h.opener = Mock()
        good = Mock()
        good.__enter__ = Mock(return_value=good)
        good.__exit__ = Mock(return_value=False)
        good.read.return_value = b'{"ok":true}'
        h.opener.open.side_effect = [
            urllib.error.HTTPError(
                "https://example.com", 503, "busy", {}, io.BytesIO(b"busy")
            ),
            good,
        ]
        reserve = Mock()
        with patch("src.http.time.sleep"):
            self.assertTrue(
                h.request("POST", "https://example.com", body={}, before=reserve)["ok"]
            )
        self.assertEqual(reserve.call_count, 2)

    def test_long_rate_limit_stops(self):
        h = Http()
        h.opener = Mock()
        h.opener.open.side_effect = urllib.error.HTTPError(
            "https://example.com",
            429,
            "limit",
            {"Retry-After": "120"},
            io.BytesIO(b"limit"),
        )
        with self.assertRaises(APIError), patch("src.http.time.sleep") as sleep:
            h.request("GET", "https://example.com")
        sleep.assert_not_called()

    def test_budget_reservation_persists(self):
        self.s.root = self.path
        (self.path / ".cache").mkdir()
        self.s.video["run_budget_usd"] = 0.2
        b = Budget(self.s, "test")
        self.addCleanup(b.db.close)
        b.reserve("API", 0.15)
        with self.assertRaises(BudgetError):
            b.reserve("API", 0.1)
        self.assertAlmostEqual(b.summary()["API"], 0.15)

    def test_responses_wire_and_cache(self):
        ai, http = self.ai([response('{"topic":"windows"}')])
        self.assertEqual(ai.structured("test", Topic).topic, "windows")
        self.assertEqual(ai.structured("test", Topic).topic, "windows")
        self.assertEqual(http.request.call_count, 1)
        p = http.request.call_args.args[3]
        self.assertEqual(p["text"]["format"]["type"], "json_schema")
        self.assertNotIn("response_format", p)

    def test_json_repair_cached(self):
        ai, http = self.ai([response("broken"), response('{"topic":"fixed"}')])
        self.assertEqual(ai.structured("test", Topic).topic, "fixed")
        self.assertEqual(ai.structured("test", Topic).topic, "fixed")
        self.assertEqual(http.request.call_count, 2)

    def test_refusal_incomplete(self):
        for value in [
            {"status": "incomplete"},
            {
                "status": "completed",
                "output": [{"content": [{"type": "refusal", "refusal": "no"}]}],
            },
        ]:
            with self.assertRaises(ProductionError):
                OpenAI.output(value)

    def test_web_forced_sources(self):
        r = response("Research")
        r["output"].append(
            {
                "type": "web_search_call",
                "action": {"sources": [{"url": "https://nasa.gov", "title": "NASA"}]},
            }
        )
        ai, http = self.ai([r])
        self.assertIn("https://nasa.gov", ai.research("question")["sources"])
        self.assertEqual(http.request.call_args.args[3]["tool_choice"], "required")

    def test_vision_wire(self):
        image = self.path / "i.jpg"
        image.write_bytes(b"fixture")
        ai, http = self.ai([response('{"topic":"green"}')])
        ai.structured("color", Topic, vision=[image], model="gpt-4.1-mini")
        content = http.request.call_args.args[3]["input"][0]["content"]
        self.assertEqual(
            content[1]["image_url"],
            "data:image/jpeg;base64," + base64.b64encode(b"fixture").decode(),
        )

    def test_pexels_endpoint_auth(self):
        http = Mock()
        http.request.return_value = {"videos": []}
        self.s.keys["PEXELS_API_KEY"] = "key"
        PexelsProvider(self.s, http, self.cache).search("window")
        args = http.request.call_args.args
        self.assertTrue(args[1].startswith("https://api.pexels.com/v1/videos/search?"))
        self.assertEqual(args[2], {"Authorization": "key"})

    def test_pixabay_cached(self):
        http = Mock()
        http.request.return_value = {"hits": []}
        provider = PixabayProvider(self.s, http, self.cache)
        provider.search("window")
        provider.search("window")
        self.assertEqual(http.request.call_count, 1)

    def test_voice_pagination(self):
        http = Mock()
        http.request.side_effect = [
            {
                "voices": [{"voice_id": "one", "category": "premade"}],
                "has_more": True,
                "next_page_token": "next",
            },
            {"voices": [{"voice_id": "two", "category": "premade"}], "has_more": False},
        ]
        voice = Voice(self.s, http, self.cache, Mock())
        self.assertEqual(voice.select(), ["one", "two"])
        self.assertIn("next_page_token=next", http.request.call_args.args[1])

    def test_alignment_mismatch_nan(self):
        a = alignment("hello")
        validate_alignment(a, "hello")
        with self.assertRaises(ProductionError):
            validate_alignment(a, "different")
        a["character_start_times_seconds"][2] = float("nan")
        with self.assertRaises(ProductionError):
            validate_alignment(a, "hello")

    def test_frame_coverage_scene_subtitle_boundaries(self):
        plan = fixture_plan()
        text = narration(plan, self.s.brand)
        t = timeline(
            plan, self.s.brand, self.s.video, alignment(text), len(text) * 0.06
        )
        self.assertEqual(sum(x["frames"] for x in t["shots"]), t["frames"])
        self.assertTrue(
            all(x["frames"] / 30 <= 2.64 for x in t["shots"] if x["scene"] is not None)
        )
        events = subtitle_events(self.s, t["words"])
        self.assertTrue(events)
        self.assertFalse(any("test." in e and "Real" in e for e in events))

    def test_disabled_intro(self):
        self.s.brand["intro_enabled"] = False
        plan = fixture_plan()
        text = narration(plan, self.s.brand)
        t = timeline(
            plan, self.s.brand, self.s.video, alignment(text), len(text) * 0.06
        )
        self.assertEqual(t["intro_end"], 0)
        self.assertEqual(t["words"][0]["text"], "Why")
        self.assertEqual(t["shots"][0]["scene"], 0)

    def test_subtitle_injection_and_focal_crop(self):
        self.assertNotIn("\\", safe("{\\pos(1,1)}hello"))
        self.assertIn(
            "0.800000",
            crop_filter({"assessment": {"focus_x": 0.8, "focus_y": 0.2}}, 1080, 1920),
        )
        self.assertIn(
            "boxblur", crop_filter({"assessment": {"crop": "contain"}}, 1080, 1920)
        )


if __name__ == "__main__":
    unittest.main()
