from pathlib import Path

from .relationship_topics import RELATIONSHIP_TOPICS
from .utils import ProductionError


SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
}

MUSIC_VOLUME_DB = -20.0


def _music_root(settings):
    return (
        Path(settings.root)
        / "assets"
        / "music"
        / "relationship"
    )


def _calm_tracks(settings):
    """
    Return all usable Calm music files.

    Tracks are sorted by filename so the rotation stays
    deterministic between runs and PC restarts.
    """

    folder = (
        _music_root(settings)
        / "calm"
    )

    if not folder.exists():
        raise ProductionError(
            "Relationship calm music folder does not exist: "
            + str(folder)
        )

    tracks = [
        path
        for path in folder.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_AUDIO_EXTENSIONS
        )
    ]

    tracks.sort(
        key=lambda path: path.name.lower()
    )

    if not tracks:
        raise ProductionError(
            "No Relationship calm music tracks found."
        )

    return tracks


def _topic_index(topic):
    """
    Return the zero-based topic index in the fixed
    Relationship queue.

    Test/unknown topics use index 0.
    """

    normalized = (
        str(topic)
        .strip()
        .lower()
    )

    for index, queue_topic in enumerate(
        RELATIONSHIP_TOPICS
    ):
        if (
            queue_topic
            .strip()
            .lower()
            == normalized
        ):
            return index

    return 0


def choose_relationship_music(
    settings,
    topic,
    mood=None,
):
    """
    Select one Calm background track.

    Current 30-day experiment:
    - Calm music only
    - deterministic rotation through every available track
    - -20 dB target volume
    - no exciting/action music

    Example with 16 tracks:
        Short 1  -> Track 1
        Short 2  -> Track 2
        ...
        Short 16 -> Track 16
        Short 17 -> Track 1
    """

    tracks = _calm_tracks(
        settings
    )

    index = _topic_index(
        topic
    )

    selected = tracks[
        index
        % len(tracks)
    ]

    print(
        (
            "[MUSIC] Calm rotation %d/%d | Track: %s"
        )
        % (
            (
                index
                % len(tracks)
            )
            + 1,
            len(tracks),
            selected.name,
        ),
        flush=True,
    )

    return {
        "path": str(
            selected
        ),
        "mood": "calm",
        "requested_mood": "calm",
        "fallback_used": False,
        "filename": selected.name,
        "volume_db": MUSIC_VOLUME_DB,
        "track_index": (
            index
            % len(tracks)
        ),
        "track_count": len(
            tracks
        ),
    }