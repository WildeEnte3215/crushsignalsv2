import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .config import Settings
from .utils import ProductionError
from .youtube_auth import get_youtube_credentials


DEFAULT_CATEGORY_ID = "24"


def _parse_publish_at(value):
    """
    Convert an ISO timestamp to YouTube-compatible UTC format.

    Example:
        2026-09-15T19:00:00+02:00
    """

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value
        )

    except ValueError as exc:
        raise ProductionError(
            "Invalid --publish-at timestamp. "
            "Use ISO format, for example: "
            "2026-09-15T19:00:00+02:00"
        ) from exc

    if dt.tzinfo is None:
        raise ProductionError(
            "--publish-at must include a timezone offset."
        )

    dt_utc = dt.astimezone(
        timezone.utc
    )

    return (
        dt_utc
        .isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


def upload_video(
    settings,
    video_path,
    title,
    description,
    tags=None,
    privacy="private",
    publish_at=None,
    category_id=DEFAULT_CATEGORY_ID,
):
    """
    Upload one video to YouTube using the official
    YouTube Data API v3.
    """

    video_path = Path(
        video_path
    )

    if not video_path.exists():
        raise ProductionError(
            "Video file does not exist: "
            + str(
                video_path
            )
        )

    if video_path.suffix.lower() != ".mp4":
        raise ProductionError(
            "YouTube uploader currently expects an MP4 file."
        )

    title = str(
        title
    ).strip()

    description = str(
        description
    ).strip()

    if not title:
        raise ProductionError(
            "YouTube title is empty."
        )

    if len(title) > 100:
        raise ProductionError(
            "YouTube title exceeds 100 characters."
        )

    if len(description) > 5000:
        raise ProductionError(
            "YouTube description exceeds 5000 characters."
        )

    if privacy not in {
        "private",
        "unlisted",
        "public",
    }:
        raise ProductionError(
            "Invalid privacy setting: "
            + str(
                privacy
            )
        )

    publish_at_utc = _parse_publish_at(
        publish_at
    )

    if publish_at_utc:
        privacy = "private"

    credentials = get_youtube_credentials(
        settings
    )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    snippet = {
        "title": title,
        "description": description,
        "categoryId": str(
            category_id
        ),
    }

    clean_tags = [
        str(tag).strip()
        for tag in (
            tags
            or []
        )
        if str(tag).strip()
    ]

    if clean_tags:
        snippet[
            "tags"
        ] = clean_tags

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }

    if publish_at_utc:
        status[
            "publishAt"
        ] = publish_at_utc

    body = {
        "snippet": snippet,
        "status": status,
    }

    media = MediaFileUpload(
        str(
            video_path
        ),
        chunksize=8 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )

    print(
        "[STEP] Uploading video to YouTube",
        flush=True,
    )

    print(
        "[INFO] Title: "
        + title,
        flush=True,
    )

    print(
        "[INFO] Privacy: "
        + privacy,
        flush=True,
    )

    if publish_at_utc:
        print(
            "[INFO] Scheduled publish time: "
            + publish_at_utc,
            flush=True,
        )

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None

        while response is None:
            upload_status, response = (
                request.next_chunk()
            )

            if upload_status:
                percent = int(
                    upload_status.progress()
                    * 100
                )

                print(
                    "[UPLOAD] %d%%"
                    % percent,
                    flush=True,
                )

    except HttpError as exc:
        raise ProductionError(
            "YouTube API upload failed: "
            + str(
                exc
            )
        ) from exc

    except Exception as exc:
        raise ProductionError(
            "YouTube upload failed: "
            + str(
                exc
            )
        ) from exc

    video_id = (
        response
        or {}
    ).get(
        "id"
    )

    if not video_id:
        raise ProductionError(
            "YouTube upload completed but returned no video ID."
        )

    print(
        "[OK] YouTube upload complete",
        flush=True,
    )

    print(
        "VIDEO_ID:",
        video_id,
        flush=True,
    )

    print(
        "URL:",
        "https://www.youtube.com/watch?v="
        + video_id,
        flush=True,
    )

    return {
        "video_id": video_id,
        "url": (
            "https://www.youtube.com/watch?v="
            + video_id
        ),
        "privacy": privacy,
        "publish_at": publish_at_utc,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Upload one rendered MP4 "
            "to YouTube."
        )
    )

    parser.add_argument(
        "--video",
        required=True,
        help="Path to MP4 video.",
    )

    parser.add_argument(
        "--title",
        required=True,
        help="YouTube video title.",
    )

    parser.add_argument(
        "--description",
        default="",
        help="YouTube description.",
    )

    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help=(
            "YouTube tag. "
            "May be supplied multiple times."
        ),
    )

    parser.add_argument(
        "--privacy",
        choices=[
            "private",
            "unlisted",
            "public",
        ],
        default="private",
    )

    parser.add_argument(
        "--publish-at",
        default=None,
        help=(
            "Optional scheduled publish time "
            "with timezone offset, for example "
            "2026-09-15T19:00:00+02:00"
        ),
    )

    args = parser.parse_args()

    try:
        settings = Settings()

        upload_video(
            settings=settings,
            video_path=args.video,
            title=args.title,
            description=args.description,
            tags=args.tag,
            privacy=args.privacy,
            publish_at=args.publish_at,
        )

        return 0

    except Exception as exc:
        print(
            "FAILED: "
            + str(
                exc
            ),
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )