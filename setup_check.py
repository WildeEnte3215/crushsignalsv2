import argparse
import datetime
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Local checks only; never prints SETUP READY",
    )

    args = parser.parse_args()
    results = []

    print("WORLD IN 60 - SETUP CHECK")

    try:
        from src.config import Settings
        from src.utils import (
            ProductionError,
            command,
            save,
            probe,
            Cache,
        )
        from src.http import Http

        settings = Settings()
        http = Http(settings.keys.values())

    except Exception as e:
        print(
            "[FAIL] Dependencies/config: %s\n"
            "Run python -m pip install -r requirements.txt"
            % e
        )
        return 1

    def test(name, fn):
        try:
            value = fn()

            if value is False:
                raise ProductionError(
                    "Check returned false"
                )

            print(
                "[OK] " + name,
                flush=True,
            )

            results.append(
                {
                    "name": name,
                    "passed": True,
                }
            )

            return value

        except Exception as e:
            reason = http.redact(e)

            print(
                "[FAIL] %s\nReason: %s"
                % (
                    name,
                    reason,
                ),
                flush=True,
            )

            results.append(
                {
                    "name": name,
                    "passed": False,
                    "reason": reason,
                }
            )

            return None

    # ---------------------------------------------------------
    # LOCAL SYSTEM CHECKS
    # ---------------------------------------------------------

    test(
        "Python >=3.9 (running %s)"
        % sys.version.split()[0],
        lambda: sys.version_info >= (
            3,
            9,
        ),
    )

    test(
        "FFmpeg",
        lambda: command(
            [
                "ffmpeg",
                "-version",
            ]
        ),
    )

    test(
        "ffprobe",
        lambda: command(
            [
                "ffprobe",
                "-version",
            ]
        ),
    )

    def filters_available():
        available = command(
            [
                "ffmpeg",
                "-hide_banner",
                "-filters",
            ]
        )

        needed = [
            "ass",
            "scale",
            "crop",
            "overlay",
            "split",
            "zoompan",
            "fps",
            "setsar",
            "fade",
            "format",
            "boxblur",
            "loudnorm",
            "aresample",
            "adelay",
            "apad",
            "amix",
            "alimiter",
            "blackdetect",
            "silencedetect",
        ]

        available_words = (
            available.split()
        )

        missing = [
            name
            for name in needed
            if not any(
                name == word
                for word
                in available_words
            )
        ]

        if missing:
            raise ProductionError(
                "FFmpeg filters missing: "
                + ", ".join(
                    missing
                )
            )

        return True

    test(
        "All production FFmpeg filters",
        filters_available,
    )

    def writable():
        output_dir = (
            settings.root
            / "output"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.TemporaryFile(
            dir=output_dir
        ) as f:
            f.write(
                b"check"
            )

        return True

    test(
        "Writable output folder",
        writable,
    )

    def render_probe():
        from src.subtitles import (
            header,
            event,
        )

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)

            ass_file = (
                p
                / "test.ass"
            )

            ass_file.write_text(
                header(
                    settings
                )
                + event(
                    0,
                    0.5,
                    "SETUP CHECK",
                )
                + "\n",
                encoding="utf-8",
            )

            font_file = (
                p
                / "font.ttf"
            )

            font_file.write_bytes(
                settings.font.read_bytes()
            )

            command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=navy:s=180x320:r=30:d=0.5",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=500:duration=0.5",
                    "-vf",
                    "ass=test.ass:fontsdir=.",
                    "-c:v",
                    "libx264",
                    "-threads",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-shortest",
                    "test.mp4",
                ],
                cwd=p,
            )

            info = probe(
                p
                / "test.mp4"
            )

            return info[
                "streams"
            ]

    test(
        "Actual H.264/AAC encode + ASS font rendering",
        render_probe,
    )

    test(
        "Configured AI provider: "
        + settings.ai_provider,
        lambda: (
            settings.ai_provider
            in (
                "gemini",
                "openai",
            )
        ),
    )

    # ---------------------------------------------------------
    # LIVE API CHECKS
    # ---------------------------------------------------------

    if not args.offline:
        from src.pipeline import clients
        from src.schemas import Topic
        from src.stock.pexels import (
            PexelsProvider,
        )
        from src.stock.fallback import (
            PixabayProvider,
        )
        from src.voice import Voice
        from src.sfx import SFX
        from src.tavily_client import Tavily
        from PIL import Image

        # Fresh cache for capability tests.
        # Production cache is not proof that the
        # current API key still has permission.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            cache = Cache(
                tmp_path
                / "cache"
            )

            (
                _,
                _,
                budget,
                ai,
            ) = clients(
                settings,
                (
                    "setup-"
                    + datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                ),
            )

            ai.cache = cache

            nonce = (
                datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
            )

            test(
                "Required API keys present",
                settings.require_keys,
            )

            # -------------------------------------------------
            # TAVILY WEB SEARCH
            # -------------------------------------------------

            if settings.keys[
                "TAVILY_API_KEY"
            ]:
                tavily = Tavily(
                    settings,
                    http,
                    cache,
                )

                def tavily_search_test():
                    result = tavily.research_search(
                        (
                            "official NASA website "
                            "National Aeronautics and "
                            "Space Administration"
                        ),
                        max_results=3,
                    )

                    if not result.get(
                        "results"
                    ):
                        raise ProductionError(
                            "Tavily returned no search results."
                        )

                    sources = tavily.sources(
                        result
                    )

                    if not sources:
                        raise ProductionError(
                            "Tavily returned no usable source URLs."
                        )

                    return True

                test(
                    (
                        "Tavily authentication + "
                        "advanced web search"
                    ),
                    tavily_search_test,
                )

            # -------------------------------------------------
            # AI PROVIDER
            # -------------------------------------------------

            if (
                settings.ai_provider
                == "gemini"
            ):
                ai_key_name = (
                    "GEMINI_API_KEY"
                )
            else:
                ai_key_name = (
                    "OPENAI_API_KEY"
                )

            if settings.keys[
                ai_key_name
            ]:
                models = list(
                    dict.fromkeys(
                        [
                            settings.video[
                                "research_model"
                            ],
                            settings.video[
                                "vision_model"
                            ],
                        ]
                    )
                )

                # ---------------------------------------------
                # GEMINI
                # ---------------------------------------------

                if (
                    settings.ai_provider
                    == "gemini"
                ):
                    for model in models:
                        test(
                            (
                                "Gemini model access: "
                                + model
                            ),
                            lambda m=model: (
                                http.request(
                                    "GET",
                                    (
                                        "https://"
                                        "generativelanguage."
                                        "googleapis.com/"
                                        "v1beta/models/"
                                        + m
                                    ),
                                    ai.headers,
                                )
                            ),
                        )

                        test(
                            (
                                "Gemini structured JSON: "
                                + model
                            ),
                            lambda m=model: (
                                ai.structured(
                                    (
                                        "Set the JSON field "
                                        "'topic' EXACTLY to "
                                        "'setup check'. "
                                        "Return no other meaning. "
                                        "Nonce: "
                                        + nonce
                                    ),
                                    Topic,
                                    model=m,
                                )
                            ),
                        )

                    def gemini_text_test():
                        payload = {
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [
                                        {
                                            "text": (
                                                "Reply with a short "
                                                "plain-text confirmation "
                                                "that says SETUP_OK. "
                                                "Nonce: "
                                                + nonce
                                            )
                                        }
                                    ],
                                }
                            ],
                            "generationConfig": {
                                "maxOutputTokens": 64,
                                "temperature": 0,
                                "thinkingConfig": {
                                    "thinkingLevel": "minimal"
                                },
                            },
                        }

                        response = ai.call(
                            payload,
                            model=settings.video[
                                "research_model"
                            ],
                        )

                        text = (
                            ai.output(
                                response
                            )
                            .strip()
                        )

                        if not text:
                            raise ProductionError(
                                "Gemini returned empty text."
                            )

                        return True

                    test(
                        "Gemini generateContent text",
                        gemini_text_test,
                    )

                    # -----------------------------------------
                    # GEMINI VISION
                    # -----------------------------------------

                    img = (
                        tmp_path
                        / "vision_test_green.jpg"
                    )

                    Image.new(
                        "RGB",
                        (
                            128,
                            128,
                        ),
                        "#00FF00",
                    ).save(
                        img,
                        quality=100,
                    )

                    def gemini_vision_test():
                        out = ai.structured(
                            (
                                "Inspect the attached image. "
                                "If its dominant visible color "
                                "belongs to the green color "
                                "family, set the JSON field "
                                "'topic' EXACTLY to GREEN. "
                                "Otherwise set it EXACTLY to "
                                "NOT_GREEN. "
                                "No explanation. "
                                "Nonce: "
                                + nonce
                            ),
                            Topic,
                            vision=[
                                img
                            ],
                            model=settings.video[
                                "vision_model"
                            ],
                        )

                        result = (
                            str(
                                out.topic
                            )
                            .strip()
                            .upper()
                        )

                        if (
                            result
                            != "GREEN"
                        ):
                            raise ProductionError(
                                (
                                    "Vision model returned "
                                    "'%s' instead of GREEN"
                                )
                                % result
                            )

                        return True

                    test(
                        (
                            "Gemini vision input "
                            "and interpretation"
                        ),
                        gemini_vision_test,
                    )

                # ---------------------------------------------
                # OPENAI FALLBACK
                # ---------------------------------------------

                elif (
                    settings.ai_provider
                    == "openai"
                ):
                    for model in models:
                        test(
                            (
                                "OpenAI model access: "
                                + model
                            ),
                            lambda m=model: (
                                http.request(
                                    "GET",
                                    (
                                        "https://api."
                                        "openai.com/v1/"
                                        "models/"
                                        + m
                                    ),
                                    ai.headers,
                                )
                            ),
                        )

                        test(
                            (
                                "OpenAI Responses "
                                "+ strict JSON: "
                                + model
                            ),
                            lambda m=model: (
                                ai.structured(
                                    (
                                        "Set topic to "
                                        "setup check. "
                                        "Nonce "
                                        + nonce
                                    ),
                                    Topic,
                                    model=m,
                                )
                            ),
                        )

                    img = (
                        tmp_path
                        / "vision_test_green.jpg"
                    )

                    Image.new(
                        "RGB",
                        (
                            128,
                            128,
                        ),
                        "#00FF00",
                    ).save(
                        img,
                        quality=100,
                    )

                    def openai_vision_test():
                        out = ai.structured(
                            (
                                "Inspect the attached image "
                                "carefully. If the dominant "
                                "visible color belongs to "
                                "the green color family, "
                                "set the JSON field 'topic' "
                                "EXACTLY to GREEN. "
                                "Otherwise set it EXACTLY "
                                "to NOT_GREEN. "
                                "No explanation. "
                                "Nonce: "
                                + nonce
                            ),
                            Topic,
                            vision=[
                                img
                            ],
                            model=settings.video[
                                "vision_model"
                            ],
                        )

                        result = (
                            str(
                                out.topic
                            )
                            .strip()
                            .upper()
                        )

                        if (
                            result
                            != "GREEN"
                        ):
                            raise ProductionError(
                                (
                                    "Vision model returned "
                                    "'%s' instead of GREEN"
                                )
                                % result
                            )

                        return True

                    test(
                        (
                            "OpenAI vision input "
                            "and interpretation"
                        ),
                        openai_vision_test,
                    )

            # -------------------------------------------------
            # PEXELS
            # -------------------------------------------------

            if settings.keys[
                "PEXELS_API_KEY"
            ]:
                test(
                    (
                        "Pexels authentication "
                        "+ video search"
                    ),
                    lambda: bool(
                        PexelsProvider(
                            settings,
                            http,
                            cache,
                        ).search(
                            "airplane window"
                        )
                    ),
                )

            # -------------------------------------------------
            # PIXABAY OPTIONAL FALLBACK
            # -------------------------------------------------

            if settings.keys[
                "PIXABAY_API_KEY"
            ]:
                test(
                    (
                        "Optional Pixabay "
                        "video search"
                    ),
                    lambda: bool(
                        PixabayProvider(
                            settings,
                            http,
                            cache,
                        ).search(
                            "airplane"
                        )
                    ),
                )

            # -------------------------------------------------
            # ELEVENLABS
            # -------------------------------------------------

            if settings.keys[
                "ELEVENLABS_API_KEY"
            ]:
                voice = Voice(
                    settings,
                    http,
                    cache,
                    budget,
                )

                sub = test(
                    (
                        "ElevenLabs authentication "
                        "+ subscription permission"
                    ),
                    voice.subscription,
                )

                if (
                    sub
                    is not None
                ):
                    test(
                        (
                            "ElevenLabs paid tier "
                            "for commercial production"
                        ),
                        lambda: (
                            sub.get(
                                "tier"
                            )
                            not in (
                                None,
                                "free",
                            )
                        ),
                    )

                def tts_model():
                    models = http.request(
                        "GET",
                        (
                            "https://api."
                            "elevenlabs.io/v1/models"
                        ),
                        voice.headers,
                    )

                    return any(
                        (
                            model.get(
                                "model_id"
                            )
                            == settings.video[
                                "tts_model"
                            ]
                            and model.get(
                                "can_do_text_to_speech"
                            )
                        )
                        for model
                        in models
                    )

                test(
                    "ElevenLabs narration model",
                    tts_model,
                )

                selected = test(
                    (
                        "Available voice + "
                        "automatic fallback selection"
                    ),
                    voice.select,
                )

                if selected:
                    test(
                        (
                            "Actual TTS, timestamps "
                            "and audio decode"
                        ),
                        lambda: voice.generate(
                            (
                                "The world explained "
                                "in sixty seconds."
                            ),
                            selected,
                        ),
                    )

                if settings.video[
                    "sfx_enabled"
                ]:
                    test(
                        (
                            "Actual SFX API "
                            "+ audio decode"
                        ),
                        lambda: SFX(
                            settings,
                            http,
                            cache,
                            budget,
                        ).generate(
                            "whoosh",
                            live_required=True,
                        ),
                    )

    # ---------------------------------------------------------
    # FINAL REPORT
    # ---------------------------------------------------------

    passed = (
        bool(
            results
        )
        and all(
            result[
                "passed"
            ]
            for result
            in results
        )
    )

    save(
        settings.root
        / "setup_report.json",
        {
            "offline": args.offline,
            "ai_provider": (
                settings.ai_provider
            ),
            "search_provider": "tavily",
            "research_model": (
                settings.video[
                    "research_model"
                ]
            ),
            "vision_model": (
                settings.video[
                    "vision_model"
                ]
            ),
            "checks": results,
            "ready": (
                passed
                and not args.offline
            ),
            "checked_at": (
                datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
            ),
        },
    )

    if (
        passed
        and args.offline
    ):
        print(
            (
                "LOCAL CHECKS PASSED - "
                "APIS NOT TESTED"
            )
        )

    elif passed:
        print(
            "SETUP READY"
        )

    else:
        print(
            "SETUP NOT READY"
        )

    return (
        0
        if passed
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
