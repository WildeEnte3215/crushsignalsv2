import os
from pathlib import Path

from dotenv import load_dotenv

from .utils import ProductionError, read


class Settings:
    def __init__(self, root=None):
        self.root = Path(
            root
            or Path(__file__).resolve().parents[1]
        ).resolve()

        # -------------------------------------------------
        # ENVIRONMENT
        # -------------------------------------------------

        load_dotenv(
            self.root / ".env",
            override=False,
        )

        # -------------------------------------------------
        # CONFIG FILES
        # -------------------------------------------------

        self.video = read(
            self.root
            / "config"
            / "video.json"
        )

        self.brand = read(
            self.root
            / "config"
            / "branding.json"
        )

        if (
            not isinstance(
                self.video,
                dict,
            )
            or not isinstance(
                self.brand,
                dict,
            )
        ):
            raise ProductionError(
                "Invalid or missing "
                "config/video.json or "
                "config/branding.json"
            )

        v = self.video
        b = self.brand

        # -------------------------------------------------
        # AI PROVIDER
        # -------------------------------------------------

        # Backward compatible:
        # old configs without ai_provider still use OpenAI.
        self.ai_provider = str(
            v.get(
                "ai_provider",
                "openai",
            )
        ).strip().lower()

        if self.ai_provider not in (
            "openai",
            "gemini",
        ):
            raise ProductionError(
                "ai_provider must be "
                "'openai' or 'gemini'."
            )

        # -------------------------------------------------
        # INTEGER SETTINGS
        # -------------------------------------------------

        for field in [
            "width",
            "height",
            "fps",
            "threads",
            "stock_candidates",
            "query_attempts",
            "max_sfx",
        ]:
            if (
                not isinstance(
                    v[field],
                    int,
                )
                or isinstance(
                    v[field],
                    bool,
                )
            ):
                raise ProductionError(
                    field
                    + " must be an integer"
                )

        # -------------------------------------------------
        # ENCODER
        # -------------------------------------------------

        if (
            not 0
            <= v["crf"]
            <= 40
            or not 1
            <= v["threads"]
            <= 32
        ):
            raise ProductionError(
                "Invalid encoder "
                "CRF/thread count"
            )

        # -------------------------------------------------
        # SOUND EFFECTS
        # -------------------------------------------------

        if (
            not 0
            <= v["sfx_volume"]
            <= 0.5
            or not 0
            <= v["max_sfx"]
            <= 12
            or v["sfx_gap_seconds"]
            < 2
        ):
            raise ProductionError(
                "Invalid SFX "
                "volume/count/spacing"
            )

        # -------------------------------------------------
        # SUBTITLES
        # -------------------------------------------------

        sub = v["subtitles"]

        if (
            not 2
            <= sub[
                "words_per_chunk"
            ]
            <= 5
            or not 0.2
            <= sub["x"]
            <= 0.8
            or not 0.3
            <= sub["y"]
            <= 0.82
        ):
            raise ProductionError(
                "Subtitle placement or "
                "chunk size outside "
                "safe bounds"
            )

        if (
            not 24
            <= sub["font_size"]
            <= 100
        ):
            raise ProductionError(
                "Subtitle font_size "
                "must be 24-100 at "
                "reference width 1080"
            )

        # -------------------------------------------------
        # BRANDING
        # -------------------------------------------------

        if (
            not 0
            < b["intro_duration"]
            <= 5
            or not 0
            < b["animation_seconds"]
            <= 5
        ):
            raise ProductionError(
                "Intro/animation durations "
                "must be positive and "
                "<=5 seconds"
            )

        if (
            b["subscribe_start"]
            < 0
            or not 0
            < b["subscribe_duration"]
            <= 10
        ):
            raise ProductionError(
                "Invalid subscribe timing"
            )

        for color in [
            b["accent"],
            b["background"],
            b["text_color"],
        ]:
            if (
                len(color) != 7
                or color[0] != "#"
                or any(
                    c
                    not in (
                        "0123456789"
                        "abcdef"
                        "ABCDEF"
                    )
                    for c
                    in color[1:]
                )
            ):
                raise ProductionError(
                    "Colors must use "
                    "#RRGGBB format"
                )

        # -------------------------------------------------
        # VIDEO DIMENSIONS
        # -------------------------------------------------

        if (
            v["width"] % 2
            or v["height"] % 2
            or min(
                v["width"],
                v["height"],
            )
            < 180
        ):
            raise ProductionError(
                "Video dimensions must "
                "be positive even numbers "
                ">=180."
            )

        # -------------------------------------------------
        # FPS / DURATION
        # -------------------------------------------------

        if not (
            1
            <= v["fps"]
            <= 60
            and 0
            < v["min_duration"]
            < v["max_duration"]
            <= 120
        ):
            raise ProductionError(
                "Invalid fps or "
                "duration bounds."
            )

        # -------------------------------------------------
        # SHOTS / STOCK
        # -------------------------------------------------

        if not (
            1
            <= v[
                "max_shot_seconds"
            ]
            <= 4
            and 1
            <= v[
                "stock_candidates"
            ]
            <= 12
        ):
            raise ProductionError(
                "Shot length must be "
                "1-4 seconds and "
                "stock_candidates 1-12."
            )

        if not (
            1
            <= v[
                "query_attempts"
            ]
            <= 5
            and 0
            <= v[
                "max_diagram_fraction"
            ]
            <= 1
        ):
            raise ProductionError(
                "Invalid search/"
                "fallback bounds."
            )

        # -------------------------------------------------
        # BUDGET
        # -------------------------------------------------

        if min(
            v[
                "run_budget_usd"
            ],
            v[
                "monthly_budget_usd"
            ],
        ) <= 0:
            raise ProductionError(
                "Budget must be positive."
            )

        # OpenAI requires local price estimates.
        # Gemini Free Tier does not need this table
        # for our local budget ledger.
        if (
            self.ai_provider
            == "openai"
        ):
            rates = v.get(
                "rates",
                {},
            )

            if (
                v[
                    "research_model"
                ]
                not in rates
                or v[
                    "vision_model"
                ]
                not in rates
            ):
                raise ProductionError(
                    "Add verified OpenAI "
                    "model prices to "
                    "video.json rates "
                    "before switching models."
                )

        # -------------------------------------------------
        # VOICE
        # -------------------------------------------------

        if not (
            0.7
            <= v[
                "voice_speed"
            ]
            <= 1.2
        ):
            raise ProductionError(
                "voice_speed must be "
                "between 0.7 and 1.2."
            )

        # -------------------------------------------------
        # FONT
        # -------------------------------------------------

        self.font = (
            self.root
            / b[
                "font_path"
            ]
        )

        if not self.font.is_file():
            raise ProductionError(
                "Font missing: "
                + str(
                    self.font
                )
            )

        # -------------------------------------------------
        # LOCAL DIRECTORIES
        # -------------------------------------------------

        for folder in [
            "output",
            ".cache",
        ]:
            (
                self.root
                / folder
            ).mkdir(
                exist_ok=True
            )

        # -------------------------------------------------
        # API KEYS
        # -------------------------------------------------

        self.keys = {
            name: os.getenv(
                name,
                "",
            ).strip()
            for name
            in [
                "OPENAI_API_KEY",
                "GEMINI_API_KEY",
                "TAVILY_API_KEY",
                "PEXELS_API_KEY",
                "ELEVENLABS_API_KEY",
                "ELEVENLABS_VOICE_ID",
                "ELEVENLABS_FALLBACK_VOICE_ID",
                "PIXABAY_API_KEY",
            ]
        }

    def require_keys(self):
        # -------------------------------------------------
        # SELECT PRIMARY AI KEY
        # -------------------------------------------------

        if (
            self.ai_provider
            == "gemini"
        ):
            ai_key = (
                "GEMINI_API_KEY"
            )

        else:
            ai_key = (
                "OPENAI_API_KEY"
            )

        required = [
            ai_key,
            "TAVILY_API_KEY",
            "PEXELS_API_KEY",
            "ELEVENLABS_API_KEY",
        ]

        missing = [
            key
            for key
            in required
            if not self.keys[
                key
            ]
        ]

        if missing:
            raise ProductionError(
                "Missing in .env: "
                + ", ".join(
                    missing
                )
                + ". See API_SETUP.md."
            )

    def prompt(
        self,
        name,
    ):
        return (
            self.root
            / "config"
            / "prompts"
            / (
                name
                + "_prompt.txt"
            )
        ).read_text(
            encoding="utf-8"
        )