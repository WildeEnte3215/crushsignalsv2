import argparse
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .history import History
from .relationship_topics import RELATIONSHIP_TOPICS
from .utils import ProductionError, RunLock
from .youtube_upload import upload_video


DEFAULT_COUNT = 5
MAX_COUNT = 50

TIMEZONE_NAME = "Europe/Berlin"

SCHEDULE_HOURS = (
    1,
    13,
    16,
    19,
    22,
)

_TIMEZONE_CACHE = None


def _timezone():
    global _TIMEZONE_CACHE

    if _TIMEZONE_CACHE is not None:
        return _TIMEZONE_CACHE

    try:
        _TIMEZONE_CACHE = ZoneInfo(
            TIMEZONE_NAME
        )

    except ZoneInfoNotFoundError:
        local_tz = (
            datetime.now()
            .astimezone()
            .tzinfo
        )

        if local_tz is None:
            raise ProductionError(
                "Could not determine local timezone. "
                "Install tzdata with: "
                "python -m pip install tzdata"
            )

        print(
            "[WARN] Europe/Berlin timezone database "
            "not available. Using Windows local timezone.",
            flush=True,
        )

        _TIMEZONE_CACHE = local_tz

    return _TIMEZONE_CACHE


def _normalize_topic(value):
    return (
        str(value)
        .strip()
        .lower()
    )


def _queue_topics():
    """
    Normalized topics belonging to the official
    Relationship production queue.
    """

    return {
        _normalize_topic(
            topic
        )
        for topic in RELATIONSHIP_TOPICS
    }


def _is_relationship_queue_run(
    run,
):
    """
    Return True only for completed Relationship runs
    belonging to RELATIONSHIP_TOPICS.
    """

    if (
        run.get(
            "mode",
            "normal",
        )
        != "relationship"
    ):
        return False

    if (
        run.get(
            "status"
        )
        != "complete"
    ):
        return False

    topic = _normalize_topic(
        run.get(
            "topic",
            "",
        )
    )

    if not topic:
        return False

    if topic not in _queue_topics():
        return False

    return True


def _already_uploaded(
    run,
    folder,
):
    """
    A run counts as uploaded if:

    - history contains youtube_video_id
    OR
    - youtube_upload.json contains video_id
    """

    if run.get(
        "youtube_video_id"
    ):
        return True

    upload_file = (
        folder
        / "youtube_upload.json"
    )

    if not upload_file.exists():
        return False

    try:
        data = json.loads(
            upload_file.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False

    return bool(
        data.get(
            "video_id"
        )
    )


def _eligible_runs(
    settings,
    history,
):
    """
    Return completed Relationship queue runs
    that have not yet been uploaded.

    Oldest completed runs are uploaded first.
    """

    result = []

    for run in history.data.get(
        "runs",
        [],
    ):
        if not _is_relationship_queue_run(
            run
        ):
            continue

        run_id = str(
            run.get(
                "id",
                "",
            )
        ).strip()

        if not run_id:
            continue

        folder = (
            Path(
                settings.root
            )
            / "output"
            / run_id
        )

        if _already_uploaded(
            run,
            folder,
        ):
            continue

        result.append(
            run
        )

    return result


def _load_relationship_short(
    folder,
):
    """
    Load generated Relationship concept JSON.
    """

    path = (
        folder
        / "relationship_short.json"
    )

    if not path.exists():
        raise ProductionError(
            "Missing relationship_short.json: "
            + str(
                path
            )
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ProductionError(
            "Could not read relationship_short.json: "
            + str(
                path
            )
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise ProductionError(
            "relationship_short.json is not a JSON object: "
            + str(
                path
            )
        )

    return data


def _clean_title(
    value,
):
    """
    Keep YouTube titles concise and valid.
    """

    title = (
        str(
            value
            or ""
        )
        .replace(
            "\r",
            " ",
        )
        .replace(
            "\n",
            " ",
        )
        .strip()
    )

    while "  " in title:
        title = title.replace(
            "  ",
            " ",
        )

    if not title:
        raise ProductionError(
            "Generated YouTube title is empty."
        )

    if len(title) > 96:
        title = (
            title[
                :96
            ]
            .rstrip(
                " ,.-:;!?"
            )
        )

    if (
        "👀" not in title
        and len(title) <= 97
    ):
        title += " 👀"

    return title


def _description_for(
    run,
    short,
):
    """
    Deterministic YouTube description.
    """

    topic = str(
        run.get(
            "topic",
            "",
        )
    ).strip()

    category = str(
        short.get(
            "category_label",
            "",
        )
    ).strip()

    if category == "FOR GIRLS":
        opener = (
            "He might be giving you more signs "
            "than you realize 👀"
        )

    elif category == "FOR BOYS":
        opener = (
            "She might be giving you more signs "
            "than you realize 👀"
        )

    else:
        opener = (
            "Sometimes the smallest signals "
            "say the most 👀"
        )

    description = (
        opener
        + "\n\n"
        + "Today's topic: "
        + topic
        + "."
        + "\n\n"
        + "New crush, attraction, texting and "
        + "relationship Shorts every day."
        + "\n\n"
        + "#shorts #crush #relationships"
    )

    return description


def _tags_for(
    run,
    short,
):
    """
    Generate compact YouTube tags.
    """

    topic = _normalize_topic(
        run.get(
            "topic",
            "",
        )
    )

    category = str(
        short.get(
            "category_label",
            "",
        )
    ).strip().upper()

    tags = [
        "crush",
        "crush signs",
        "relationships",
        "relationship advice",
        "dating",
        "attraction",
        "love signs",
        "relationship shorts",
        "crush facts",
    ]

    if (
        "text" in topic
        or "message" in topic
    ):
        tags.extend(
            [
                "texting",
                "texting signs",
            ]
        )

    if "school" in topic:
        tags.extend(
            [
                "school crush",
                "school relationship",
            ]
        )

    if (
        category == "FOR GIRLS"
        or " he " in (
            " "
            + topic
            + " "
        )
        or "guy" in topic
    ):
        tags.extend(
            [
                "he likes you",
                "signs he likes you",
            ]
        )

    if (
        category == "FOR BOYS"
        or " she " in (
            " "
            + topic
            + " "
        )
        or "girl" in topic
    ):
        tags.extend(
            [
                "she likes you",
                "signs she likes you",
            ]
        )

    result = []
    seen = set()

    for tag in tags:
        clean = (
            str(tag)
            .strip()
            .lower()
        )

        if not clean:
            continue

        if clean in seen:
            continue

        seen.add(
            clean
        )

        result.append(
            clean
        )

    return result


def _save_upload_sidecar(
    folder,
    run,
    result,
    title,
    description,
    tags,
):
    """
    Save YouTube upload metadata beside the Short.
    """

    data = {
        "run_id": run.get(
            "id"
        ),
        "topic": run.get(
            "topic"
        ),
        "video_id": result.get(
            "video_id"
        ),
        "url": result.get(
            "url"
        ),
        "privacy": result.get(
            "privacy",
            "private",
        ),
        "publish_at": result.get(
            "publish_at"
        ),
        "title": title,
        "description": description,
        "tags": tags,
    }

    path = (
        folder
        / "youtube_upload.json"
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _parse_publish_time(
    value,
):
    """
    Parse a stored YouTube publish timestamp.

    youtube_upload.py normally stores UTC:
        2026-09-22T14:00:00Z
    """

    value = str(
        value
        or ""
    ).strip()

    if not value:
        return None

    if value.endswith(
        "Z"
    ):
        value = (
            value[:-1]
            + "+00:00"
        )

    try:
        dt = datetime.fromisoformat(
            value
        )

    except ValueError:
        return None

    if dt.tzinfo is None:
        return None

    return dt.astimezone(
        _timezone()
    )


def _latest_recorded_publish_at(
    settings,
    history,
):
    """
    Find the latest scheduled publication that our
    automatic uploader previously created.

    Reads both history and youtube_upload.json.
    """

    found = []

    for run in history.data.get(
        "runs",
        [],
    ):
        dt = _parse_publish_time(
            run.get(
                "youtube_publish_at"
            )
        )

        if dt is not None:
            found.append(
                dt
            )

    output_dir = (
        Path(
            settings.root
        )
        / "output"
    )

    if output_dir.exists():
        for path in output_dir.rglob(
            "youtube_upload.json"
        ):
            try:
                data = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ):
                continue

            dt = _parse_publish_time(
                data.get(
                    "publish_at"
                )
            )

            if dt is not None:
                found.append(
                    dt
                )

    if not found:
        return None

    return max(
        found
    )


def _next_publish_slot(
    after_dt,
):
    """
    Return the first regular publishing slot
    strictly after after_dt.

    Daily chronological slots:

        01:00
        13:00
        16:00
        19:00
        22:00

    Example:

        22 Sep 16:00
        22 Sep 19:00
        22 Sep 22:00
        23 Sep 01:00
        23 Sep 13:00
    """

    tz = _timezone()

    local = after_dt.astimezone(
        tz
    )

    for day_offset in range(
        0,
        4,
    ):
        day = (
            local.date()
            + timedelta(
                days=day_offset
            )
        )

        for hour in SCHEDULE_HOURS:
            candidate = datetime.combine(
                day,
                time(
                    hour=hour,
                    minute=0,
                    second=0,
                ),
                tzinfo=tz,
            )

            if candidate > local:
                return candidate

    raise ProductionError(
        "Could not calculate next YouTube schedule slot."
    )


def _initial_publish_slot(
    start_at,
):
    """
    Create the exact first automatic publishing slot.

    Format:
        YYYY-MM-DDTHH:MM

    Example:
        2026-09-22T16:00
    """

    try:
        naive = datetime.strptime(
            start_at,
            "%Y-%m-%dT%H:%M",
        )

    except ValueError as exc:
        raise ProductionError(
            "Invalid --start-at. "
            "Use YYYY-MM-DDTHH:MM, for example "
            "2026-09-22T16:00"
        ) from exc

    slot = naive.replace(
        tzinfo=_timezone()
    )

    now = datetime.now(
        _timezone()
    )

    minimum_future = (
        now
        + timedelta(
            minutes=5
        )
    )

    if slot <= minimum_future:
        raise ProductionError(
            "--start-at must be at least 5 minutes "
            "in the future."
        )

    return slot


def _build_schedule(
    first_slot,
    count,
):
    """
    Build N consecutive publishing slots.

    The first slot is used exactly as supplied.
    Every later video follows the normal slot sequence.
    """

    schedule = [
        first_slot
    ]

    while len(
        schedule
    ) < count:
        schedule.append(
            _next_publish_slot(
                schedule[-1]
            )
        )

    return schedule


def _format_local_time(
    dt,
):
    return dt.strftime(
        "%Y-%m-%d %H:%M"
    )


def run_batch_upload(
    settings,
    count=DEFAULT_COUNT,
    start_at=None,
):
    """
    Upload and schedule the next N completed
    Relationship Shorts.

    First automatic batch:
        use --start-at

    Later batches:
        previous schedule metadata determines
        the next free slot automatically.
    """

    if count < 1:
        raise ProductionError(
            "Upload count must be at least 1."
        )

    if count > MAX_COUNT:
        raise ProductionError(
            "Upload count may not exceed %d."
            % MAX_COUNT
        )

    history = History(
        settings.root
    )

    eligible = _eligible_runs(
        settings,
        history,
    )

    selected = eligible[
        :count
    ]

    if not selected:
        print(
            "[OK] No new completed Relationship Shorts "
            "need uploading.",
            flush=True,
        )

        return []

    latest_publish = (
        _latest_recorded_publish_at(
            settings,
            history,
        )
    )

    if latest_publish is None:
        if not start_at:
            raise ProductionError(
                "No automatic YouTube schedule exists yet. "
                "Run the first scheduled batch with "
                "--start-at YYYY-MM-DDTHH:MM. "
                "Example: "
                "--start-at 2026-09-22T16:00"
            )

        first_slot = _initial_publish_slot(
            start_at
        )

    else:
        if start_at:
            print(
                "[INFO] Existing automatic schedule found. "
                "--start-at is ignored.",
                flush=True,
            )

        now = datetime.now(
            _timezone()
        )

        minimum_future = (
            now
            + timedelta(
                minutes=5
            )
        )

        anchor = max(
            latest_publish,
            minimum_future,
        )

        first_slot = _next_publish_slot(
            anchor
        )

    schedule = _build_schedule(
        first_slot,
        len(
            selected
        ),
    )

    print(
        (
            "[YOUTUBE BATCH] Uploading and scheduling "
            "%d Short%s"
        )
        % (
            len(
                selected
            ),
            (
                ""
                if len(
                    selected
                ) == 1
                else "s"
            ),
        ),
        flush=True,
    )

    print(
        "[INFO] Schedule timezone: "
        + TIMEZONE_NAME,
        flush=True,
    )

    print(
        "[INFO] Daily slots: "
        "01:00, 13:00, 16:00, 19:00, 22:00",
        flush=True,
    )

    print(
        "",
        flush=True,
    )

    print(
        "[SCHEDULE PREVIEW]",
        flush=True,
    )

    for index, (
        run,
        publish_dt,
    ) in enumerate(
        zip(
            selected,
            schedule,
        ),
        start=1,
    ):
        print(
            (
                " %d. %s | %s"
            )
            % (
                index,
                _format_local_time(
                    publish_dt
                ),
                run.get(
                    "topic",
                    "",
                ),
            ),
            flush=True,
        )

    results = []

    for index, (
        run,
        publish_dt,
    ) in enumerate(
        zip(
            selected,
            schedule,
        ),
        start=1,
    ):
        run_id = str(
            run[
                "id"
            ]
        )

        topic = str(
            run.get(
                "topic",
                "",
            )
        ).strip()

        folder = (
            Path(
                settings.root
            )
            / "output"
            / run_id
        )

        video_path = (
            folder
            / "final.mp4"
        )

        print(
            "",
            flush=True,
        )

        print(
            (
                "[YOUTUBE %d/%d] %s"
            )
            % (
                index,
                len(
                    selected
                ),
                topic,
            ),
            flush=True,
        )

        if not video_path.exists():
            raise ProductionError(
                "Missing final.mp4 for run: "
                + run_id
            )

        short = _load_relationship_short(
            folder
        )

        title = _clean_title(
            short.get(
                "youtube_title"
            )
            or topic
        )

        description = _description_for(
            run,
            short,
        )

        tags = _tags_for(
            run,
            short,
        )

        publish_iso = publish_dt.isoformat(
            timespec="seconds"
        )

        print(
            "[INFO] Prepared title: "
            + title,
            flush=True,
        )

        print(
            "[INFO] Scheduled publication: "
            + _format_local_time(
                publish_dt
            )
            + " "
            + TIMEZONE_NAME,
            flush=True,
        )

        print(
            "[INFO] Upload privacy: "
            "private until scheduled release",
            flush=True,
        )

        try:
            result = upload_video(
                settings=settings,
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                privacy="private",
                publish_at=publish_iso,
            )

        except Exception:
            print(
                (
                    "[YOUTUBE] FAILED on run %s"
                    % run_id
                ),
                file=sys.stderr,
                flush=True,
            )

            raise

        video_id = result.get(
            "video_id"
        )

        url = result.get(
            "url"
        )

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
            youtube_privacy="private",
            youtube_uploaded=True,
            youtube_publish_at=result.get(
                "publish_at"
            ),
        )

        result[
            "run_id"
        ] = run_id

        result[
            "topic"
        ] = topic

        result[
            "title"
        ] = title

        result[
            "scheduled_local"
        ] = _format_local_time(
            publish_dt
        )

        results.append(
            result
        )

        print(
            "[YOUTUBE] Saved upload + schedule metadata",
            flush=True,
        )

    print(
        "",
        flush=True,
    )

    print(
        (
            "[YOUTUBE BATCH DONE] %d Short%s "
            "uploaded and scheduled."
        )
        % (
            len(
                results
            ),
            (
                ""
                if len(
                    results
                ) == 1
                else "s"
            ),
        ),
        flush=True,
    )

    for result in results:
        print(
            (
                " - %s | %s | %s"
            )
            % (
                result.get(
                    "scheduled_local",
                    "",
                ),
                result.get(
                    "title",
                    "",
                ),
                result.get(
                    "url",
                    "",
                ),
            ),
            flush=True,
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Upload completed Relationship Shorts "
            "and automatically schedule them on YouTube."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=(
            "Number of Shorts to upload and schedule. "
            "Default: 5. Maximum: 50."
        ),
    )

    parser.add_argument(
        "--start-at",
        default=None,
        help=(
            "Exact first automatic publishing slot. "
            "Format: YYYY-MM-DDTHH:MM. "
            "Example: 2026-09-22T16:00. "
            "Only needed for the first automatic batch."
        ),
    )

    args = parser.parse_args()

    try:
        settings = Settings()

        with RunLock(
            settings.root
            / ".youtube_upload.lock"
        ):
            run_batch_upload(
                settings,
                count=args.count,
                start_at=args.start_at,
            )

        return 0

    except Exception as exc:
        message = str(
            exc
        )

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
            "FAILED: "
            + message,
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )