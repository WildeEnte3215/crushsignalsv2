import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings
from .history import History
from .relationship_topics import RELATIONSHIP_TOPICS
from .utils import ProductionError, RunLock
from .youtube_upload import upload_video
from .youtube_batch_upload import (
    _normalize_topic,
    _already_uploaded,
    _load_relationship_short,
    _clean_title,
    _description_for,
    _tags_for,
    _save_upload_sidecar,
)

DEFAULT_COUNT = 25
MAX_COUNT = 25
TIMEZONE = ZoneInfo("Europe/Berlin")
START_DATE = dt.date(2026, 10, 1)
END_DATE = dt.date(2026, 10, 16)

BACKFILL_TIMES = (
    (2, 30),
    (4, 30),
    (6, 30),
    (8, 30),
    (10, 30),
    (12, 0),
    (14, 30),
    (17, 30),
    (20, 30),
    (23, 30),
)

NEW_TOPICS = RELATIONSHIP_TOPICS[180:]


def _folder_for(settings, run):
    return Path(settings.root) / "output" / str(run["id"])


def _completed_new_runs(settings, history):
    wanted = {
        _normalize_topic(topic): index
        for index, topic in enumerate(NEW_TOPICS)
    }

    by_topic = {}

    for run in history.data.get("runs", []):
        if run.get("mode") != "relationship":
            continue

        if run.get("status") != "complete":
            continue

        key = _normalize_topic(run.get("topic", ""))

        if key not in wanted:
            continue

        folder = _folder_for(settings, run)

        if not (folder / "final.mp4").exists():
            continue

        by_topic[key] = run

    result = []

    for topic in NEW_TOPICS:
        run = by_topic.get(_normalize_topic(topic))

        if run is not None:
            result.append(run)

    return result


def _parse_publish_at(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        value = dt.datetime.fromisoformat(text)
    except ValueError:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=TIMEZONE)

    return value.astimezone(TIMEZONE)


def _used_publish_times(settings):
    used = set()
    output_dir = Path(settings.root) / "output"

    if not output_dir.exists():
        return used

    for path in output_dir.rglob("youtube_upload.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            continue

        value = _parse_publish_at(data.get("publish_at"))

        if value is None:
            continue

        used.add(
            value.replace(second=0, microsecond=0)
        )

    return used


def _all_backfill_slots():
    slots = []
    day = START_DATE

    while day <= END_DATE:
        for hour, minute in BACKFILL_TIMES:
            slots.append(
                dt.datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    minute,
                    tzinfo=TIMEZONE,
                )
            )

        day += dt.timedelta(days=1)

    return slots


def _available_slots(settings):
    used = _used_publish_times(settings)

    return [
        slot
        for slot in _all_backfill_slots()
        if slot.replace(second=0, microsecond=0) not in used
    ]


def _eligible_new_runs(settings, history):
    result = []

    for run in _completed_new_runs(settings, history):
        folder = _folder_for(settings, run)

        if _already_uploaded(run, folder):
            continue

        result.append(run)

    return result


def _print_status(settings, history):
    completed = _completed_new_runs(settings, history)
    eligible = _eligible_new_runs(settings, history)
    slots = _available_slots(settings)

    print()
    print("=== YOUTUBE BACKFILL STATUS ===")
    print("Neue Topics fertig:", len(completed), "/ 160")
    print("Noch nicht auf YouTube:", len(eligible))
    print("Freie Backfill-Slots:", len(slots), "/ 160")
    print("Zeitraum: 01.10.2026 - 16.10.2026")
    print("Zusatz-Slots pro Tag: 10")
    print()


def run_backfill(settings, count=DEFAULT_COUNT, dry_run=False):
    if count < 1:
        raise ProductionError("Count must be at least 1.")

    if count > MAX_COUNT:
        raise ProductionError(
            "Count may not exceed %d." % MAX_COUNT
        )

    history = History(settings.root)

    _print_status(settings, history)

    eligible = _eligible_new_runs(settings, history)
    slots = _available_slots(settings)

    if not eligible:
        print("[OK] No new Relationship Shorts need YouTube backfill upload.")
        return []

    if not slots:
        raise ProductionError(
            "No free YouTube backfill slots remain between "
            "2026-10-01 and 2026-10-16."
        )

    selected = eligible[:count]
    selected_slots = slots[:len(selected)]

    if len(selected_slots) < len(selected):
        raise ProductionError(
            "Not enough free backfill slots remain."
        )

    print("[BACKFILL] Next %d Shorts:" % len(selected))

    for index, (run, slot) in enumerate(
        zip(selected, selected_slots),
        start=1,
    ):
        print(
            "%02d. %s | %s"
            % (
                index,
                slot.strftime("%d.%m.%Y %H:%M"),
                run.get("topic", ""),
            )
        )

    if dry_run:
        print()
        print("[DRY RUN] Nothing uploaded.")
        return []

    results = []

    for index, (run, slot) in enumerate(
        zip(selected, selected_slots),
        start=1,
    ):
        run_id = str(run["id"])
        topic = str(run.get("topic", "")).strip()
        folder = _folder_for(settings, run)
        video_path = folder / "final.mp4"

        if not video_path.exists():
            raise ProductionError(
                "Missing final.mp4 for run: " + run_id
            )

        short = _load_relationship_short(folder)

        title = _clean_title(
            short.get("youtube_title") or topic
        )

        description = _description_for(run, short)
        tags = _tags_for(run, short)
        publish_at = slot.isoformat(timespec="seconds")

        print()
        print(
            "[BACKFILL %d/%d] %s"
            % (index, len(selected), topic)
        )
        print(
            "[SCHEDULE] %s Europe/Berlin"
            % slot.strftime("%d.%m.%Y %H:%M")
        )

        try:
            result = upload_video(
                settings=settings,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy="private",
                publish_at=publish_at,
            )
        except Exception:
            print(
                "[BACKFILL] FAILED on run %s" % run_id,
                file=sys.stderr,
                flush=True,
            )
            raise

        video_id = result.get("video_id")
        url = result.get("url")

        if not video_id:
            raise ProductionError(
                "YouTube upload returned no video ID."
            )

        _save_upload_sidecar(
            folder=folder,
            run=run,
            result=result,
            title=title,
            description=description,
            tags=tags,
        )

        history.update(
            run,
            youtube_video_id=video_id,
            youtube_url=url,
            youtube_privacy=result.get(
                "privacy",
                "private",
            ),
            youtube_uploaded=True,
            youtube_publish_at=result.get(
                "publish_at"
            ),
        )

        result["run_id"] = run_id
        result["topic"] = topic
        result["title"] = title
        result["local_publish_at"] = slot.isoformat()

        results.append(result)

        print("[OK] Uploaded and scheduled")

    print()
    print(
        "[BACKFILL DONE] %d Shorts uploaded and scheduled."
        % len(results)
    )

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Upload the 160 newly appended Relationship Shorts "
            "into the extra YouTube slots from Oct 1-16, 2026."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="Number to upload. Default/max: 25.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the next assignments without uploading.",
    )

    args = parser.parse_args()

    try:
        settings = Settings()

        with RunLock(
            settings.root / ".youtube_backfill_upload.lock"
        ):
            run_backfill(
                settings,
                count=args.count,
                dry_run=args.dry_run,
            )

        return 0

    except Exception as exc:
        message = str(exc)

        if "settings" in locals():
            try:
                for secret in settings.keys.values():
                    if secret:
                        message = message.replace(
                            secret,
                            "[REDACTED]",
                        )
            except Exception:
                pass

        print(
            "FAILED: " + message,
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
