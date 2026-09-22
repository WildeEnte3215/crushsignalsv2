import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


DEFAULT_API_VERSION = "v26.0"
REQUEST_TIMEOUT = 60
UPLOAD_TIMEOUT = 300


class FacebookUploadError(RuntimeError):
    pass


# ============================================================
# ENV
# ============================================================

def _load_env():
    load_dotenv(override=True)

    page_id = os.getenv(
        "FACEBOOK_PAGE_ID",
        "",
    ).strip()

    page_token = os.getenv(
        "FACEBOOK_PAGE_TOKEN",
        "",
    ).strip()

    api_version = os.getenv(
        "FACEBOOK_API_VERSION",
        DEFAULT_API_VERSION,
    ).strip()

    if not page_id:
        raise FacebookUploadError(
            "FACEBOOK_PAGE_ID fehlt in .env"
        )

    if not page_token:
        raise FacebookUploadError(
            "FACEBOOK_PAGE_TOKEN fehlt in .env"
        )

    return (
        page_id,
        page_token,
        api_version,
    )


# ============================================================
# META HELPERS
# ============================================================

def _safe_json(response):
    try:
        return response.json()

    except Exception:
        return {
            "raw_response": response.text[:1000]
        }


def _raise_for_meta_error(
    response,
    context,
):
    data = _safe_json(
        response
    )

    if (
        response.ok
        and "error" not in data
    ):
        return data

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

    parts = [
        f"{context} fehlgeschlagen",
        f"HTTP {response.status_code}",
        str(message),
    ]

    if code is not None:
        parts.append(
            f"Code {code}"
        )

    if subcode is not None:
        parts.append(
            f"Subcode {subcode}"
        )

    raise FacebookUploadError(
        " | ".join(parts)
    )


# ============================================================
# PAGE CHECK
# ============================================================

def verify_page(
    page_id,
    page_token,
    api_version,
):
    url = (
        "https://graph.facebook.com/"
        f"{api_version}/{page_id}"
    )

    response = requests.get(
        url,
        params={
            "fields": "id,name",
            "access_token": page_token,
        },
        timeout=REQUEST_TIMEOUT,
    )

    data = _raise_for_meta_error(
        response,
        "Facebook-Seite pruefen",
    )

    return data


# ============================================================
# REEL SESSION
# ============================================================

def create_reel_session(
    page_id,
    page_token,
    api_version,
):
    """
    Erstellt eine Reel-Upload-Session
    direkt fuer die Facebook-Seite.

    Wichtig:
    Kein /me/video_reels mehr.

    System-User-Tokens muessen explizit
    ueber die Facebook-Page-ID arbeiten.
    """

    url = (
        "https://graph.facebook.com/"
        f"{api_version}/"
        f"{page_id}/video_reels"
    )

    response = requests.post(
        url,
        params={
            "access_token": page_token,
            "upload_phase": "start",
        },
        timeout=REQUEST_TIMEOUT,
    )

    data = _raise_for_meta_error(
        response,
        "Reel-Upload-Session starten",
    )

    video_id = data.get(
        "video_id"
    )

    upload_url = data.get(
        "upload_url"
    )

    if not video_id:
        raise FacebookUploadError(
            "Meta hat keine video_id "
            "zurueckgegeben."
        )

    if not upload_url:
        raise FacebookUploadError(
            "Meta hat keine upload_url "
            "zurueckgegeben."
        )

    return (
        video_id,
        upload_url,
    )


# ============================================================
# FILE UPLOAD
# ============================================================

def upload_local_video(
    video_path,
    upload_url,
    page_token,
):
    video_path = Path(
        video_path
    ).resolve()

    if not video_path.exists():
        raise FacebookUploadError(
            f"Videodatei nicht gefunden: "
            f"{video_path}"
        )

    if not video_path.is_file():
        raise FacebookUploadError(
            f"Pfad ist keine Datei: "
            f"{video_path}"
        )

    file_size = (
        video_path
        .stat()
        .st_size
    )

    if file_size <= 0:
        raise FacebookUploadError(
            "Videodatei ist leer."
        )

    headers = {
        "Authorization":
            f"OAuth {page_token}",
        "offset":
            "0",
        "file_size":
            str(file_size),
        "Content-Type":
            "application/octet-stream",
    }

    with video_path.open(
        "rb"
    ) as handle:

        response = requests.post(
            upload_url,
            headers=headers,
            data=handle,
            timeout=UPLOAD_TIMEOUT,
        )

    data = _raise_for_meta_error(
        response,
        "Videodatei hochladen",
    )

    if data.get(
        "success"
    ) is not True:

        raise FacebookUploadError(
            "Meta meldet keinen "
            "erfolgreichen Upload: "
            f"{data}"
        )

    return data


# ============================================================
# REEL STATUS
# ============================================================

def get_reel_status(
    video_id,
    page_token,
    api_version,
):
    url = (
        "https://graph.facebook.com/"
        f"{api_version}/{video_id}"
    )

    response = requests.get(
        url,
        params={
            "fields": "status",
            "access_token": page_token,
        },
        timeout=REQUEST_TIMEOUT,
    )

    return _raise_for_meta_error(
        response,
        "Reel-Status abrufen",
    )


def wait_for_upload_complete(
    video_id,
    page_token,
    api_version,
    timeout_seconds=120,
):
    deadline = (
        time.time()
        + timeout_seconds
    )

    last_status = None

    while (
        time.time()
        < deadline
    ):
        data = get_reel_status(
            video_id,
            page_token,
            api_version,
        )

        status = data.get(
            "status",
            {},
        )

        last_status = status

        uploading = (
            status
            .get(
                "uploading_phase",
                {},
            )
            .get(
                "status"
            )
        )

        print(
            "Upload-Status: "
            f"{uploading or 'unbekannt'}"
        )

        if uploading == "complete":
            return status

        if uploading in {
            "error",
            "failed",
        }:
            raise FacebookUploadError(
                "Facebook meldet "
                "Uploadfehler: "
                f"{status}"
            )

        time.sleep(
            2
        )

    raise FacebookUploadError(
        "Timeout beim Warten auf "
        "Abschluss des Uploads. "
        f"Letzter Status: "
        f"{last_status}"
    )


# ============================================================
# PUBLISH
# ============================================================

def publish_reel(
    page_id,
    video_id,
    page_token,
    api_version,
    title="",
    description="",
    video_state="PUBLISHED",
):
    """
    Schliesst den Reel-Upload
    fuer die konkrete Facebook-Seite ab.
    """

    url = (
        "https://graph.facebook.com/"
        f"{api_version}/"
        f"{page_id}/video_reels"
    )

    params = {
        "access_token":
            page_token,
        "video_id":
            video_id,
        "upload_phase":
            "finish",
        "video_state":
            video_state,
    }

    if title:
        params[
            "title"
        ] = title

    if description:
        params[
            "description"
        ] = description

    response = requests.post(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    data = _raise_for_meta_error(
        response,
        "Reel veroeffentlichen",
    )

    if data.get(
        "success"
    ) is not True:

        raise FacebookUploadError(
            "Meta meldet "
            "Veroeffentlichung nicht "
            "als erfolgreich: "
            f"{data}"
        )

    return data


# ============================================================
# PROCESSING STATUS
# ============================================================

def wait_for_processing(
    video_id,
    page_token,
    api_version,
    timeout_seconds=180,
):
    deadline = (
        time.time()
        + timeout_seconds
    )

    last_status = None

    while (
        time.time()
        < deadline
    ):
        data = get_reel_status(
            video_id,
            page_token,
            api_version,
        )

        status = data.get(
            "status",
            {},
        )

        last_status = status

        video_status = status.get(
            "video_status",
            "unbekannt",
        )

        processing = (
            status
            .get(
                "processing_phase",
                {},
            )
            .get(
                "status"
            )
        )

        publishing = (
            status
            .get(
                "publishing_phase",
                {},
            )
            .get(
                "status"
            )
        )

        progress = status.get(
            "processing_progress"
        )

        print(
            "Verarbeitung: "
            f"video={video_status} | "
            f"processing={processing} | "
            f"publishing={publishing} | "
            f"progress={progress}"
        )

        if (
            publishing
            == "complete"
        ):
            return status

        if video_status in {
            "ready",
            "published",
        }:
            return status

        if processing in {
            "error",
            "failed",
        }:
            raise FacebookUploadError(
                "Facebook-Verarbeitung "
                "fehlgeschlagen: "
                f"{status}"
            )

        if publishing in {
            "error",
            "failed",
        }:
            raise FacebookUploadError(
                "Facebook-"
                "Veroeffentlichung "
                "fehlgeschlagen: "
                f"{status}"
            )

        time.sleep(
            3
        )

    print(
        "Hinweis: Reel wurde an "
        "Facebook uebergeben, aber "
        "die Verarbeitung laeuft "
        "moeglicherweise noch."
    )

    return last_status


# ============================================================
# FULL UPLOAD
# ============================================================

def upload_reel(
    video_path,
    title="",
    description="",
    video_state="PUBLISHED",
):
    (
        page_id,
        page_token,
        api_version,
    ) = _load_env()

    video_path = Path(
        video_path
    ).resolve()

    print("")
    print(
        "=== Facebook Reel Upload ==="
    )
    print(
        f"Datei: {video_path.name}"
    )
    print(
        f"API: {api_version}"
    )
    print("")

    # --------------------------------------------------------
    # 1
    # --------------------------------------------------------

    print(
        "[1/6] Facebook-Seite "
        "pruefen ..."
    )

    page = verify_page(
        page_id,
        page_token,
        api_version,
    )

    print(
        "OK: "
        f"{page.get('name')} "
        f"({page.get('id')})"
    )

    # --------------------------------------------------------
    # 2
    # --------------------------------------------------------

    print("")
    print(
        "[2/6] Upload-Session "
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

    # --------------------------------------------------------
    # 3
    # --------------------------------------------------------

    print("")
    print(
        "[3/6] MP4 hochladen ..."
    )

    file_size_mb = (
        video_path
        .stat()
        .st_size
        / 1024
        / 1024
    )

    print(
        "Dateigroesse: "
        f"{file_size_mb:.2f} MB"
    )

    upload_local_video(
        video_path,
        upload_url,
        page_token,
    )

    print(
        "OK: Datei uebertragen"
    )

    # --------------------------------------------------------
    # 4
    # --------------------------------------------------------

    print("")
    print(
        "[4/6] Upload-Status "
        "pruefen ..."
    )

    wait_for_upload_complete(
        video_id,
        page_token,
        api_version,
    )

    print(
        "OK: Upload vollstaendig"
    )

    # --------------------------------------------------------
    # 5
    # --------------------------------------------------------

    print("")
    print(
        "[5/6] Reel "
        "veroeffentlichen ..."
    )

    publish_reel(
        page_id,
        video_id,
        page_token,
        api_version,
        title=title,
        description=description,
        video_state=video_state,
    )

    print(
        "OK: Facebook hat Reel "
        f"akzeptiert ({video_state})"
    )

    # --------------------------------------------------------
    # 6
    # --------------------------------------------------------

    print("")
    print(
        "[6/6] Verarbeitung "
        "pruefen ..."
    )

    final_status = (
        wait_for_processing(
            video_id,
            page_token,
            api_version,
        )
    )

    print("")
    print(
        "=== FERTIG ==="
    )

    print(
        "Facebook Video-ID: "
        f"{video_id}"
    )

    if final_status:
        print(
            "Letzter Status: "
            f"{final_status.get('video_status', 'unbekannt')}"
        )

    print("")

    return {
        "video_id":
            video_id,
        "page_id":
            page_id,
        "state":
            video_state,
        "status":
            final_status,
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Laedt ein lokales Video "
            "als Facebook Reel auf "
            "CrushSignals hoch."
        )
    )

    parser.add_argument(
        "--video",
        required=True,
        help=(
            "Pfad zur lokalen MP4-Datei"
        ),
    )

    parser.add_argument(
        "--title",
        default="",
        help=(
            "Optionaler Reel-Titel"
        ),
    )

    parser.add_argument(
        "--description",
        default="",
        help=(
            "Optionaler Beschreibungstext"
        ),
    )

    parser.add_argument(
        "--state",
        default="PUBLISHED",
        choices=[
            "PUBLISHED",
            "DRAFT",
        ],
        help=(
            "Veroeffentlichungsstatus"
        ),
    )

    args = parser.parse_args()

    try:
        upload_reel(
            video_path=args.video,
            title=args.title,
            description=args.description,
            video_state=args.state,
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
            "FACEBOOK UPLOAD FEHLER:"
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