"""CLI entry point; configuration and dotenv load before any API client exists."""

import argparse
import datetime
import sys


def main():
    parser = argparse.ArgumentParser(
        description="World in 60 production engine"
    )

    parser.add_argument(
        "--topic"
    )

    parser.add_argument(
        "--resume",
        help="Run ID from history.json",
    )

    parser.add_argument(
        "--new",
        action="store_true",
        help="Start new despite unfinished run",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Offline diagnostic; no paid APIs",
    )

    parser.add_argument(
        "--mode",
        choices=[
            "normal",
            "scam",
            "relationship",
        ],
        default=None,
        help="Production mode",
    )

    args = parser.parse_args()

    try:
        from src.config import Settings
        from src.utils import ProductionError, RunLock

        settings = Settings()

        from src.http import Http

        with RunLock(
            settings.root / ".run.lock"
        ):
            if args.demo:
                from src.demo import demo

                print(
                    demo(settings)
                )

                return 0

            settings.require_keys()

            from src.history import History

            history = History(
                settings.root
            )

            # -------------------------------------------------
            # RESUME EXISTING RUN
            # -------------------------------------------------

            if args.resume:
                run = next(
                    (
                        r
                        for r in history.data["runs"]
                        if r["id"] == args.resume
                    ),
                    None,
                )

                if not run:
                    raise ProductionError(
                        "Unknown run ID: "
                        + args.resume
                    )

                mode = run.get(
                    "mode",
                    "normal",
                )

                if (
                    args.mode is not None
                    and args.mode != mode
                ):
                    raise ProductionError(
                        (
                            "Run %s belongs to mode '%s', "
                            "not '%s'."
                        )
                        % (
                            args.resume,
                            mode,
                            args.mode,
                        )
                    )

            # -------------------------------------------------
            # NEW / UNFINISHED RUN
            # -------------------------------------------------

            else:
                mode = (
                    args.mode
                    or "normal"
                )

                run = (
                    None
                    if (
                        args.new
                        or args.topic
                    )
                    else history.unfinished(
                        mode=mode
                    )
                )

            # -------------------------------------------------
            # CREATE NEW RUN
            # -------------------------------------------------

            if run is None:
                if args.topic:
                    topic = (
                        args.topic
                    )

                elif mode in (
                    "scam",
                    "relationship",
                ):
                    raise ProductionError(
                        (
                            "%s mode currently requires --topic. "
                            "Automatic topic generation will be added later."
                        )
                        % mode.capitalize()
                    )

                else:
                    from src.pipeline import clients
                    from src.topics import choose

                    (
                        _,
                        _,
                        _,
                        ai,
                    ) = clients(
                        settings,
                        (
                            "topic-"
                            + datetime.datetime.now().isoformat()
                        ),
                    )

                    topic = choose(
                        ai,
                        [
                            r["topic"]
                            for r in history.data["runs"]
                            if (
                                r["status"]
                                == "complete"
                                and r.get(
                                    "mode",
                                    "normal",
                                )
                                == "normal"
                            )
                        ],
                    )

                run = history.new(
                    topic,
                    mode=mode,
                )

            # -------------------------------------------------
            # MODE FROM STORED RUN
            # -------------------------------------------------

            mode = run.get(
                "mode",
                "normal",
            )

            history.update(
                run,
                status="running",
            )

            try:
                # ---------------------------------------------
                # SCAM / SAFETY TEXT SHORT
                # ---------------------------------------------

                if mode == "scam":
                    from src.scam_pipeline import produce_scam

                    final = produce_scam(
                        settings,
                        run,
                    )

                # ---------------------------------------------
                # RELATIONSHIP / CRUSH TEXT SHORT
                # ---------------------------------------------

                elif mode == "relationship":
                    from src.relationship_pipeline import produce_relationship

                    final = produce_relationship(
                        settings,
                        run,
                    )

                # ---------------------------------------------
                # ORIGINAL WORLD IN 60 PIPELINE
                # ---------------------------------------------

                else:
                    from src.pipeline import produce

                    final = produce(
                        settings,
                        run,
                    )

                history.update(
                    run,
                    status="complete",
                    final=str(
                        final
                    ),
                    error=None,
                )

            except Exception as e:
                history.update(
                    run,
                    status="failed",
                    error=Http(
                        settings.keys.values()
                    ).redact(
                        e
                    ),
                )

                raise

            print(
                "DONE: "
                + str(
                    final
                )
            )

            return 0

    except ImportError as e:
        print(
            (
                "Dependency missing: %s. "
                "Run python -m pip install "
                "-r requirements.txt"
            )
            % e,
            file=sys.stderr,
        )

        return 1

    except Exception as e:
        message = str(
            e
        )

        if "settings" in locals():
            for secret in settings.keys.values():
                if secret:
                    message = message.replace(
                        secret,
                        "[REDACTED]",
                    )

        print(
            "FAILED: "
            + message,
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )