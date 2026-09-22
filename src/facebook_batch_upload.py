import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .facebook_upload import (
    FacebookUploadError,
    _load_env,
    create_reel_session,
    upload_local_video,
    wait_for_upload_complete,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"

FACEBOOK_SIDECAR = "facebook_upload.json"

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

REQUEST_TIMEOUT = 60


def _timezone():
    try:
        return ZoneInfo(TIMEZONE_NAME)
    except Exception:
        return datetime.now().astimezone().tzinfo


def _read_json(path):
    path = Path(path)

    if not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def _write_json(path, data):
    path = Path(path)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _find_string(obj, keys):
    if isinstance(obj, dict):

        for key in keys:
            value = obj.get(key)

            if (
                isinstance(value, str)
                and value.strip()
            ):
                return value.strip()

        for value in obj.values():
            found = _find_string(
                value,
                keys,
            )

            if found:
                return found

    elif isinstance(obj, list):

        for value in obj:
            found = _find_string(
                value,
                keys,
            )

            if found:
                return found

    return None


def _folder_slug_to_topic(
    folder_name,
):
    name = str(folder_name)

    name = re.sub(
        r"^\d{8}_\d{6}_\d+_",
        "",
        name,
    )

    name = name.replace(
        "_",
        " ",
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name


def _clean_title(text):
    text = str(
        text or ""
    ).strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    if not text:
        return "CrushSignals"

    return text[:255]


def _is_relationship_run(
    run_dir,
):
    run_dir = Path(run_dir)

    return (
        (
            run_dir
            / "relationship_short.json"
        ).exists()
        or
        (
            run_dir
            / "relationship_metadata.json"
        ).exists()
    )


def _topic_for_run(
    run_dir,
):
    run_dir = Path(run_dir)

    candidates = [
        run_dir
        / "relationship_short.json",

        run_dir
        / "relationship_metadata.json",
    ]

    keys = (
        "topic",
        "title",
        "video_title",
        "youtube_title",
        "headline",
        "hook",
    )

    for path in candidates:

        data = _read_json(
            path
        )

        found = _find_string(
            data,
            keys,
        )

        if found:
            return found

    return _folder_slug_to_topic(
        run_dir.name
    )


def _final_video(
    run_dir,
):
    return (
        Path(run_dir)
        / "final.mp4"
    )


def _sidecar_path(
    run_dir,
):
    return (
        Path(run_dir)
        / FACEBOOK_SIDECAR
    )


def _sidecar(
    run_dir,
):
    return _read_json(
        _sidecar_path(
            run_dir
        )
    )


def _already_uploaded(
    run_dir,
):
    data = _sidecar(
        run_dir
    )

    if not data:
        return False

    if (
        data.get(
            "facebook_uploaded"
        )
        is True
    ):
        return True

    if (
        data.get(
            "facebook_video_id"
        )
        and
        data.get(
            "facebook_state"
        )
        in {
            "PUBLISHED",
            "SCHEDULED",
        }
    ):
        return True

    return False


def _save_sidecar(
    run_dir,
    *,
    topic,
    title,
    description,
    video_id,
    state,
    publish_at,
):
    tz = _timezone()

    data = {
        "facebook_uploaded":
            True,

        "facebook_video_id":
            str(video_id),

        "facebook_state":
            state,

        "facebook_publish_at":
            (
                publish_at.isoformat()
                if publish_at
                else None
            ),

        "facebook_publish_at_utc":
            (
                publish_at
                .astimezone(
                    timezone.utc
                )
                .isoformat()
                if publish_at
                else None
            ),

        "facebook_topic":
            topic,

        "facebook_title":
            title,

        "facebook_description":
            description,

        "facebook_uploaded_at":
            datetime.now(
                tz
            ).isoformat(),
    }

    _write_json(
        _sidecar_path(
            run_dir
        ),
        data,
    )


def _eligible_runs():
    if not OUTPUT_DIR.exists():
        return []

    runs = []

    for run_dir in (
        OUTPUT_DIR.iterdir()
    ):
        if not run_dir.is_dir():
            continue

        if not _is_relationship_run(
            run_dir
        ):
            continue

        video = _final_video(
            run_dir
        )

        if not video.exists():
            continue

        if _already_uploaded(
            run_dir
        ):
            continue

        runs.append(
            run_dir
        )

    runs.sort(
        key=lambda p: p.name
    )

    return runs


def _hashtags_for(
    topic,
):
    text = str(
        topic or ""
    ).lower()

    tags = [
        "#CrushSignals"
    ]

    if any(
        word in text
        for word in (
            "text",
            "message",
            "reply",
            "snap",
            "instagram",
            "dm",
        )
    ):
        tags += [
            "#Texting",
            "#Crush",
            "#DatingAdvice",
        ]

    elif any(
        word in text
        for word in (
            "red flag",
            "green flag",
            "relationship",
            "losing interest",
            "toxic",
        )
    ):
        tags += [
            "#Relationships",
            "#DatingAdvice",
            "#Love",
        ]

    elif any(
        word in text
        for word in (
            "date",
            "dating",
            "first move",
            "flirt",
        )
    ):
        tags += [
            "#Dating",
            "#DatingAdvice",
            "#Relationships",
        ]

    elif any(
        word in text
        for word in (
            "crush",
            "likes you",
            "attracted",
            "attraction",
            "secretly",
        )
    ):
        tags += [
            "#Crush",
            "#Dating",
            "#Relationships",
        ]

    else:
        tags += [
            "#Crush",
            "#DatingAdvice",
            "#Relationships",
        ]

    return " ".join(
        tags[:4]
    )


def _description_for(
    topic,
):
    topic = str(
        topic or ""
    ).strip()

    if not topic:
        topic = (
            "Crush, dating & "
            "relationship signals"
        )

    questions = (
        "Have you noticed any "
        "of these before? 👀",

        "Which one do you "
        "recognize the most? 👀",

        "Would you notice "
        "these signs? 👀",

        "Which one surprised "
        "you the most?",

        "Have you ever "
        "experienced this?",

        "Which sign do you "
        "think is the most obvious?",
    )

    question_index = (
        sum(
            ord(char)
            for char in topic
        )
        % len(questions)
    )

    question = (
        questions[
            question_index
        ]
    )

    hashtags = _hashtags_for(
        topic
    )

    return (
        f"{topic}\n\n"
        f"{question}\n\n"
        "Follow CrushSignals "
        "for daily crush, dating "
        "& relationship signals.\n\n"
        f"{hashtags}"
    )


def _title_for(
    topic,
):
    topic = str(
        topic
    ).strip()

    if not topic:
        return "CrushSignals"

    return _clean_title(
        (
            topic[0].upper()
            + topic[1:]
        )
        if len(topic) > 1
        else topic.upper()
    )


def _parse_start_at(
    value,
):
    if not value:
        return None

    tz = _timezone()

    try:
        dt = datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M",
        )

    except ValueError as exc:
        raise FacebookUploadError(
            "--start-at muss dieses "
            "Format haben: "
            "YYYY-MM-DDTHH:MM"
        ) from exc

    return dt.replace(
        tzinfo=tz
    )


def _latest_recorded_publish_at():
    tz = _timezone()
    latest = None

    if not OUTPUT_DIR.exists():
        return None

    for run_dir in (
        OUTPUT_DIR.iterdir()
    ):
        if not run_dir.is_dir():
            continue

        data = _sidecar(
            run_dir
        )

        value = data.get(
            "facebook_publish_at"
        )

        if not value:
            continue

        try:
            dt = (
                datetime
                .fromisoformat(
                    value
                )
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=tz
                )

            dt = dt.astimezone(
                tz
            )

        except Exception:
            continue

        if (
            latest is None
            or dt > latest
        ):
            latest = dt

    return latest


def _next_publish_slot(
    after_dt,
):
    tz = _timezone()

    after_dt = (
        after_dt.astimezone(
            tz
        )
    )

    for day_offset in range(
        0,
        10,
    ):
        date = (
            after_dt.date()
            + timedelta(
                days=day_offset
            )
        )

        for hour in sorted(
            SCHEDULE_HOURS
        ):
            candidate = datetime(
                year=date.year,
                month=date.month,
                day=date.day,
                hour=hour,
                minute=0,
                second=0,
                tzinfo=tz,
            )

            if candidate > after_dt:
                return candidate

    raise FacebookUploadError(
        "Kein naechster "
        "Facebook-Slot gefunden."
    )


def _initial_publish_slot(
    start_at=None,
):
    tz = _timezone()

    now = datetime.now(
        tz
    )

    if start_at is not None:

        if (
            start_at
            <=
            now
            + timedelta(
                minutes=10
            )
        ):
            raise FacebookUploadError(
                "--start-at muss mindestens "
                "10 Minuten in der Zukunft liegen."
            )

        return start_at

    latest = (
        _latest_recorded_publish_at()
    )

    if latest is not None:
        return _next_publish_slot(
            latest
        )

    return _next_publish_slot(
        now
        + timedelta(
            minutes=10
        )
    )


def _build_schedule(
    count,
    start_at=None,
):
    first = _initial_publish_slot(
        start_at
    )

    slots = [
        first
    ]

    while len(slots) < count:
        slots.append(
            _next_publish_slot(
                slots[-1]
            )
        )

    return slots


def _format_local_time(
    dt,
):
    return dt.strftime(
        "%d.%m.%Y %H:%M"
    )


def _safe_json(
    response,
):
    try:
        return response.json()

    except Exception:
        return {
            "raw_response":
                response.text[:1000]
        }


def _finish_scheduled_reel(
    *,
    page_id,
    video_id,
    page_token,
    api_version,
    publish_at,
    title,
    description,
):
    """
    Schliesst den Reel-Upload ab
    und plant ihn serverseitig
    fuer die konkrete Facebook-Seite.
    """

    url = (
        "https://graph.facebook.com/"
        f"{api_version}/"
        f"{page_id}/video_reels"
    )

    unix_timestamp = int(
        publish_at.timestamp()
    )

    params = {
        "access_token":
            page_token,

        "video_id":
            video_id,

        "upload_phase":
            "finish",

        "video_state":
            "SCHEDULED",

        "scheduled_publish_time":
            str(
                unix_timestamp
            ),

        "title":
            title,

        "description":
            description,
    }

    response = requests.post(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    data = _safe_json(
        response
    )

    if (
        not response.ok
        or "error" in data
    ):
        error = data.get(
            "error",
            {},
        )

        message = error.get(
            "message",
            data.get(
                "raw_response",
                f"HTTP {response.status_code}",
            ),
        )

        code = error.get(
            "code"
        )

        subcode = error.get(
            "error_subcode"
        )

        raise FacebookUploadError(
            "Facebook-Scheduling "
            "fehlgeschlagen"
            f" | HTTP {response.status_code}"
            f" | {message}"
            f" | Code {code}"
            f" | Subcode {subcode}"
        )

    if (
        data.get(
            "success"
        )
        is not True
    ):
        raise FacebookUploadError(
            "Facebook hat Scheduling "
            "nicht als erfolgreich "
            f"bestaetigt: {data}"
        )

    return data


def _upload_scheduled_run(
    run_dir,
    publish_at,
):
    run_dir = Path(
        run_dir
    )

    (
        page_id,
        page_token,
        api_version,
    ) = _load_env()

    video_path = _final_video(
        run_dir
    )

    topic = _topic_for_run(
        run_dir
    )

    title = _title_for(
        topic
    )

    description = (
        _description_for(
            topic
        )
    )

    print("")
    print(
        "=" * 70
    )

    print(
        f"Topic: {topic}"
    )

    print(
        "Geplant: "
        f"{_format_local_time(publish_at)} "
        f"{TIMEZONE_NAME}"
    )

    print(
        f"Datei: {video_path.name}"
    )

    print(
        "=" * 70
    )

    print(
        "[1/4] Upload-Session "
        "starten ..."
    )

    (
        video_id,
        upload_url,
    ) = create_reel_session(
        page_id,
        page_token,
        api_version,
    )

    print(
        f"OK: Video-ID {video_id}"
    )

    print(
        "[2/4] MP4 hochladen ..."
    )

    upload_local_video(
        video_path,
        upload_url,
        page_token,
    )

    print(
        "OK: Datei uebertragen"
    )

    print(
        "[3/4] Upload pruefen ..."
    )

    wait_for_upload_complete(
        video_id,
        page_token,
        api_version,
    )

    print(
        "OK: Upload vollstaendig"
    )

    print(
        "[4/4] Reel bei "
        "Facebook planen ..."
    )

    _finish_scheduled_reel(
        page_id=page_id,
        video_id=video_id,
        page_token=page_token,
        api_version=api_version,
        publish_at=publish_at,
        title=title,
        description=description,
    )

    _save_sidecar(
        run_dir,
        topic=topic,
        title=title,
        description=description,
        video_id=video_id,
        state="SCHEDULED",
        publish_at=publish_at,
    )

    print(
        "OK: Facebook Reel geplant"
    )

    print(
        "Publish: "
        f"{_format_local_time(publish_at)}"
    )

    return {
        "run_dir":
            str(
                run_dir
            ),

        "video_id":
            str(
                video_id
            ),

        "topic":
            topic,

        "publish_at":
            publish_at.isoformat(),
    }


def run_batch(
    *,
    count,
    start_at=None,
    dry_run=False,
):
    if count < 1:
        raise FacebookUploadError(
            "--count muss mindestens "
            "1 sein."
        )

    if count > MAX_COUNT:
        raise FacebookUploadError(
            "--count darf maximal "
            f"{MAX_COUNT} sein."
        )

    queue = _eligible_runs()

    print("")
    print(
        "=== Facebook "
        "Relationship Queue ==="
    )

    print(
        "Noch nicht auf Facebook: "
        f"{len(queue)}"
    )

    if not queue:
        print(
            "Keine offenen "
            "Relationship-Videos."
        )

        return []

    selected = queue[
        :count
    ]

    schedule = _build_schedule(
        len(selected),
        start_at=start_at,
    )

    print(
        "Fuer diesen Lauf: "
        f"{len(selected)}"
    )

    print("")

    for index, (
        run_dir,
        publish_at,
    ) in enumerate(
        zip(
            selected,
            schedule,
        ),
        start=1,
    ):
        topic = _topic_for_run(
            run_dir
        )

        print(
            f"{index}. "
            f"{_format_local_time(publish_at)} "
            f"| {topic}"
        )

    if dry_run:
        print("")
        print(
            "DRY RUN: "
            "Es wurde nichts hochgeladen."
        )

        return []

    results = []

    print("")
    print(
        "Starte Facebook "
        "Batch Upload ..."
    )

    for index, (
        run_dir,
        publish_at,
    ) in enumerate(
        zip(
            selected,
            schedule,
        ),
        start=1,
    ):
        print("")
        print(
            f"### FACEBOOK "
            f"{index}/"
            f"{len(selected)} ###"
        )

        try:
            result = (
                _upload_scheduled_run(
                    run_dir,
                    publish_at,
                )
            )

            results.append(
                result
            )

        except Exception as exc:
            print("")
            print(
                "FACEBOOK BATCH FEHLER:"
            )

            print(
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print("")

            print(
                "Batch wird hier "
                "gestoppt, damit nichts "
                "doppelt hochgeladen wird."
            )

            raise

    print("")
    print(
        "=" * 70
    )

    print(
        "FACEBOOK BATCH FERTIG"
    )

    print(
        "Erfolgreich geplant: "
        f"{len(results)}"
    )

    if results:
        print(
            "Erster Slot: "
            f"{_format_local_time(schedule[0])}"
        )

        print(
            "Letzter Slot: "
            f"{_format_local_time(schedule[len(results) - 1])}"
        )

    print(
        "=" * 70
    )

    print("")

    return results


def main():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Plant Relationship-Reels "
                "automatisch auf Facebook."
            )
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=(
            "Anzahl der Reels. "
            f"Standard {DEFAULT_COUNT}, "
            f"maximal {MAX_COUNT}."
        ),
    )

    parser.add_argument(
        "--start-at",
        default=None,
        help=(
            "Optionaler erster "
            "Publish-Termin in "
            "Europe/Berlin. "
            "Format: YYYY-MM-DDTHH:MM"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Nur Queue und Zeitplan "
            "anzeigen, nichts hochladen."
        ),
    )

    args = parser.parse_args()

    try:
        start_at = _parse_start_at(
            args.start_at
        )

        run_batch(
            count=args.count,
            start_at=start_at,
            dry_run=args.dry_run,
        )

    except KeyboardInterrupt:
        print("")
        print(
            "Abgebrochen."
        )

        sys.exit(
            130
        )

    except FacebookUploadError as exc:
        print("")
        print(
            "FACEBOOK FEHLER:"
        )

        print(
            exc
        )

        sys.exit(
            1
        )

    except Exception as exc:
        print("")
        print(
            "UNERWARTETER FEHLER:"
        )

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        sys.exit(
            1
        )


if __name__ == "__main__":
    main()