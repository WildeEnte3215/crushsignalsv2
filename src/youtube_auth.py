from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .utils import ProductionError


YOUTUBE_UPLOAD_SCOPE = (
    "https://www.googleapis.com/auth/youtube.upload"
)


def _oauth_client_path(settings):
    return (
        Path(settings.root)
        / "config"
        / "youtube_oauth_client.json"
    )


def _token_path(settings):
    return (
        Path(settings.root)
        / "config"
        / "youtube_token.json"
    )


def get_youtube_credentials(settings):
    """
    Return valid YouTube OAuth credentials.

    First run:
    - opens Google login in the browser
    - user approves access
    - stores refresh/access token locally

    Later runs:
    - reuses the stored token
    - refreshes automatically when required
    """

    client_path = _oauth_client_path(
        settings
    )

    token_path = _token_path(
        settings
    )

    if not client_path.exists():
        raise ProductionError(
            "Missing YouTube OAuth client file: "
            + str(client_path)
        )

    scopes = [
        YOUTUBE_UPLOAD_SCOPE
    ]

    credentials = None

    # -----------------------------------------------------
    # LOAD EXISTING TOKEN
    # -----------------------------------------------------

    if token_path.exists():
        try:
            credentials = (
                Credentials.from_authorized_user_file(
                    str(token_path),
                    scopes=scopes,
                )
            )

        except Exception as exc:
            raise ProductionError(
                "Could not read YouTube OAuth token: "
                + str(exc)
            ) from exc

    # -----------------------------------------------------
    # REFRESH EXISTING TOKEN
    # -----------------------------------------------------

    if (
        credentials
        and credentials.expired
        and credentials.refresh_token
    ):
        print(
            "[STEP] Refreshing YouTube OAuth token",
            flush=True,
        )

        try:
            credentials.refresh(
                Request()
            )

        except Exception as exc:
            raise ProductionError(
                "Could not refresh YouTube OAuth token: "
                + str(exc)
            ) from exc

    # -----------------------------------------------------
    # FIRST-TIME LOGIN
    # -----------------------------------------------------

    if (
        credentials is None
        or not credentials.valid
    ):
        print(
            "[STEP] Opening Google login for YouTube access",
            flush=True,
        )

        try:
            flow = (
                InstalledAppFlow.from_client_secrets_file(
                    str(client_path),
                    scopes=scopes,
                )
            )

            credentials = flow.run_local_server(
                host="localhost",
                port=0,
                open_browser=True,
                authorization_prompt_message=(
                    "Authorize CrushSignals Uploader "
                    "in the opened browser."
                ),
                success_message=(
                    "YouTube authorization complete. "
                    "You can close this browser tab."
                ),
                access_type="offline",
                prompt="consent",
            )

        except Exception as exc:
            raise ProductionError(
                "YouTube OAuth login failed: "
                + str(exc)
            ) from exc

    # -----------------------------------------------------
    # SAVE TOKEN
    # -----------------------------------------------------

    try:
        token_path.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    except OSError as exc:
        raise ProductionError(
            "Could not save YouTube OAuth token: "
            + str(exc)
        ) from exc

    print(
        "[OK] YouTube OAuth credentials ready",
        flush=True,
    )

    return credentials


def main():
    from .config import Settings

    settings = Settings()

    credentials = get_youtube_credentials(
        settings
    )

    print(
        "VALID:",
        bool(
            credentials.valid
        ),
    )

    print(
        "REFRESH_TOKEN:",
        bool(
            credentials.refresh_token
        ),
    )

    print(
        "TOKEN_FILE:",
        str(
            _token_path(
                settings
            )
        ),
    )


if __name__ == "__main__":
    main()