import argparse
import sys

from .config import Settings
from .history import History
from .http import Http
from .relationship_pipeline import produce_relationship
from .relationship_topics import RELATIONSHIP_TOPICS
from .utils import ProductionError, RunLock


def _completed_topics(history):
    """
    Return all successfully completed Relationship topics.
    """

    return {
        str(run.get("topic", "")).strip().lower()
        for run in history.data["runs"]
        if (
            run.get("status") == "complete"
            and run.get(
                "mode",
                "normal",
            )
            == "relationship"
        )
    }


def _unfinished_run_for_topic(
    history,
    topic,
):
    """
    Reuse an unfinished/failed Relationship run
    for the same topic instead of creating a duplicate.
    """

    wanted = (
        str(topic)
        .strip()
        .lower()
    )

    for run in reversed(
        history.data["runs"]
    ):
        if (
            run.get(
                "mode",
                "normal",
            )
            != "relationship"
        ):
            continue

        if (
            str(
                run.get(
                    "topic",
                    "",
                )
            )
            .strip()
            .lower()
            != wanted
        ):
            continue

        if run.get(
            "status"
        ) != "complete":
            return run

    return None


def _next_topics(
    history,
    count,
):
    """
    Select the next Relationship topics that have not
    already been completed.
    """

    completed = _completed_topics(
        history
    )

    remaining = [
        topic
        for topic in RELATIONSHIP_TOPICS
        if (
            topic.strip().lower()
            not in completed
        )
    ]

    return remaining[
        :count
    ]


def run_batch(
    settings,
    count=5,
):
    """
    Produce the next N Relationship Shorts.

    Stops immediately on the first real failure to avoid
    wasting API credits when a systemic problem exists.
    """

    if count < 1:
        raise ProductionError(
            "Batch count must be at least 1."
        )

    if count > 50:
        raise ProductionError(
            "Batch count may not exceed 50."
        )

    history = History(
        settings.root
    )

    topics = _next_topics(
        history,
        count,
    )

    if not topics:
        print(
            "[OK] All Relationship topics are already complete.",
            flush=True,
        )

        return []

    print(
        (
            "[BATCH] Producing %d Relationship Shorts"
            % len(
                topics
            )
        ),
        flush=True,
    )

    completed_outputs = []

    for index, topic in enumerate(
        topics,
        start=1,
    ):
        print(
            "",
            flush=True,
        )

        print(
            (
                "[BATCH %d/%d] %s"
                % (
                    index,
                    len(
                        topics
                    ),
                    topic,
                )
            ),
            flush=True,
        )

        run = _unfinished_run_for_topic(
            history,
            topic,
        )

        if run is None:
            run = history.new(
                topic,
                mode="relationship",
            )

            print(
                "[BATCH] Created new run: "
                + run["id"],
                flush=True,
            )

        else:
            print(
                "[BATCH] Resuming run: "
                + run["id"],
                flush=True,
            )

        history.update(
            run,
            status="running",
        )

        try:
            final = produce_relationship(
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

            completed_outputs.append(
                str(
                    final
                )
            )

            print(
                "[BATCH] Complete: "
                + str(
                    final
                ),
                flush=True,
            )

        except Exception as exc:
            redacted = Http(
                settings.keys.values()
            ).redact(
                exc
            )

            history.update(
                run,
                status="failed",
                error=redacted,
            )

            print(
                (
                    "[BATCH] FAILED on %s"
                    % topic
                ),
                file=sys.stderr,
                flush=True,
            )

            raise

    print(
        "",
        flush=True,
    )

    print(
        (
            "[BATCH DONE] %d Relationship Shorts completed."
            % len(
                completed_outputs
            )
        ),
        flush=True,
    )

    for output in completed_outputs:
        print(
            " - "
            + output,
            flush=True,
        )

    return completed_outputs


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Produce the next Relationship Shorts "
            "from the fixed topic queue."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help=(
            "Number of Shorts to produce. "
            "Default: 5. Maximum: 10."
        ),
    )

    args = parser.parse_args()

    try:
        settings = Settings()

        settings.require_keys()

        with RunLock(
            settings.root
            / ".run.lock"
        ):
            run_batch(
                settings,
                count=args.count,
            )

        return 0

    except Exception as exc:
        message = str(
            exc
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