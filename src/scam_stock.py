import json
from pathlib import Path

from .stock.pexels import PexelsProvider
from .utils import (
    ProductionError,
    valid_media,
)


BACKGROUND_REUSE_WINDOW = 50


def _candidate_score(
    candidate,
    minimum_duration,
):
    """
    Lower tuple = better candidate.

    Candidates reaching this function must already:
    - be portrait
    - have dimensions
    - have a Pexels ID
    - be long enough for the narration

    Priority:
    1. close to 9:16
    2. useful resolution
    3. longer clip as final tie-breaker
    """

    width = candidate.get(
        "width",
        0,
    )

    height = candidate.get(
        "height",
        0,
    )

    duration = candidate.get(
        "duration",
        0,
    )

    if not width or not height:
        return (
            99,
            99,
            99,
        )

    ratio = (
        width
        / height
    )

    target_ratio = (
        9
        / 16
    )

    ratio_difference = abs(
        ratio
        - target_ratio
    )

    short_edge = min(
        width,
        height,
    )

    return (
        ratio_difference,
        -short_edge,
        -duration,
    )


def _normalize_pexels_id(value):
    """
    Normalize Pexels IDs so int/string differences
    cannot accidentally allow duplicates.
    """

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return value


def _used_pexels_ids(
    settings,
    reuse_window=BACKGROUND_REUSE_WINDOW,
):
    """
    Return Pexels IDs used by the most recent Shorts.

    A background becomes eligible again once it has not
    appeared within the most recent `reuse_window` Shorts.
    """

    output_dir = (
        Path(
            settings.root
        )
        / "output"
    )

    if not output_dir.exists():
        return set()

    metadata_files = list(
        output_dir.rglob(
            "*_metadata.json"
        )
    )

    # Output folder names start with timestamps in this project.
    # Newest folders therefore sort first by parent folder name.
    metadata_files.sort(
        key=lambda path: path.parent.name,
        reverse=True,
    )

    used = set()
    valid_backgrounds_seen = 0

    for metadata_path in metadata_files:
        try:
            data = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            continue

        background = data.get(
            "background"
        )

        if not isinstance(
            background,
            dict,
        ):
            continue

        provider = str(
            background.get(
                "provider",
                "",
            )
        ).strip().lower()

        if (
            provider
            and provider != "pexels"
        ):
            continue

        pexels_id = _normalize_pexels_id(
            background.get(
                "id"
            )
        )

        if not pexels_id:
            continue

        valid_backgrounds_seen += 1

        used.add(
            pexels_id
        )

        if (
            valid_backgrounds_seen
            >= reuse_window
        ):
            break

    return used


def _usable_candidates(
    candidates,
    minimum_duration,
):
    """
    Keep only candidates that:

    - can be downloaded
    - have dimensions
    - have a Pexels ID
    - are portrait
    - are long enough for the full narration
    """

    usable = []

    for candidate in candidates:
        if not candidate.get(
            "download"
        ):
            continue

        width = candidate.get(
            "width"
        )

        height = candidate.get(
            "height"
        )

        if not width or not height:
            continue

        try:
            width = int(
                width
            )

            height = int(
                height
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if height <= width:
            continue

        if not candidate.get(
            "id"
        ):
            continue

        try:
            duration = float(
                candidate.get(
                    "duration",
                    0,
                )
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if duration < minimum_duration:
            continue

        usable.append(
            candidate
        )

    return usable


def _fresh_candidates(
    candidates,
    used_ids,
):
    """
    Remove Pexels clips used within the active reuse window.
    """

    result = []

    for candidate in candidates:
        candidate_id = _normalize_pexels_id(
            candidate.get(
                "id"
            )
        )

        if not candidate_id:
            continue

        if candidate_id in used_ids:
            continue

        result.append(
            candidate
        )

    return result


def _merge_candidates(
    target,
    candidates,
):
    """
    Merge search results without duplicating the same
    Pexels video inside the current candidate pool.
    """

    known_ids = {
        _normalize_pexels_id(
            candidate.get(
                "id"
            )
        )
        for candidate in target
    }

    for candidate in candidates:
        candidate_id = _normalize_pexels_id(
            candidate.get(
                "id"
            )
        )

        if not candidate_id:
            continue

        if candidate_id in known_ids:
            continue

        target.append(
            candidate
        )

        known_ids.add(
            candidate_id
        )


def _search_queries(
    query,
):
    """
    Build a broad search list.

    Start close to the generated concept and then widen the
    search so production does not stall on a narrow Pexels query.
    """

    queries = [
        query,
        query + " vertical",
        query + " portrait video",
        query + " vertical cinematic",
        query + " vertical aesthetic",
        query + " vertical lifestyle",
        query + " portrait people",

        "person texting on phone vertical",
        "young person using smartphone vertical",
        "young person using smartphone at night vertical",
        "smartphone texting close up portrait",
        "person looking at phone indoors vertical",
        "phone notification night aesthetic vertical",
        "young woman smartphone city night vertical",
        "young man smartphone city night vertical",
        "person waiting for text message vertical",
        "person reading message phone vertical",
        "young adult texting cafe vertical",
        "smartphone lifestyle portrait video",

        "young person city night vertical",
        "city lights portrait video",
        "dreamy urban night vertical",
        "young adult walking city night vertical",
        "night street lifestyle portrait",
        "city bokeh people vertical",
        "cinematic night portrait video",
        "urban lights vertical lifestyle",
        "young people city lights vertical",
        "dreamy night city portrait video",

        "romantic sunset lifestyle vertical",
        "young adult walking city vertical",
        "aesthetic cafe people vertical",
        "young person window light portrait video",
        "cinematic city night vertical",
        "young people lifestyle portrait video",
        "sunset city walking vertical",
        "dreamy urban lights vertical video",
        "young adult cafe portrait video",
        "young person sunset vertical",
        "young people walking city portrait",
        "cinematic lifestyle people vertical",
        "young adult indoors aesthetic vertical",
        "young person city portrait video",
        "soft light portrait lifestyle vertical",
        "urban lifestyle young people vertical",
        "young adult evening city vertical",
        "aesthetic people portrait video",
    ]

    unique = []
    seen = set()

    for item in queries:
        clean = str(
            item
        ).strip()

        if not clean:
            continue

        key = clean.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            clean
        )

    return unique


def choose_scam_background(
    settings,
    http,
    cache,
    query,
    minimum_duration=8.0,
):
    """
    Find and download one suitable portrait Pexels background.

    Rules:
    - Never reuse a Pexels ID used within the last 50 Shorts.
    - Older backgrounds may be recycled after that window.
    - Never select a video shorter than the narration.
    - Only use portrait footage.
    - Try broad fallback searches before failing.
    """

    query = str(
        query
    ).strip()

    if not query:
        raise ProductionError(
            "Background search query is empty."
        )

    minimum_duration = float(
        minimum_duration
    )

    provider = PexelsProvider(
        settings,
        http,
        cache,
    )

    used_ids = _used_pexels_ids(
        settings
    )

    if used_ids:
        print(
            (
                "[INFO] Avoiding %d Pexels background%s "
                "used within the last %d Shorts"
            )
            % (
                len(
                    used_ids
                ),
                (
                    ""
                    if len(
                        used_ids
                    ) == 1
                    else "s"
                ),
                BACKGROUND_REUSE_WINDOW,
            ),
            flush=True,
        )

    print(
        (
            "[INFO] Background must be at least %.2fs long"
        )
        % minimum_duration,
        flush=True,
    )

    print(
        "[INFO] Background must be portrait",
        flush=True,
    )

    search_queries = _search_queries(
        query
    )

    all_usable = []

    selected = None
    selected_query = query

    for index, search_query in enumerate(
        search_queries,
        start=1,
    ):
        if index == 1:
            print(
                "[STEP] Searching Pexels background: "
                + search_query,
                flush=True,
            )

        else:
            print(
                "[STEP] Searching alternate Pexels background: "
                + search_query,
                flush=True,
            )

        candidates = provider.search(
            search_query
        )

        usable = _usable_candidates(
            candidates,
            minimum_duration,
        )

        _merge_candidates(
            all_usable,
            usable,
        )

        fresh = _fresh_candidates(
            all_usable,
            used_ids,
        )

        if not fresh:
            continue

        fresh.sort(
            key=lambda candidate: _candidate_score(
                candidate,
                minimum_duration,
            )
        )

        selected = fresh[0]
        selected_query = search_query

        break

    if not all_usable:
        raise ProductionError(
            (
                "Pexels returned no unused portrait background "
                "long enough for %.2fs narration. Query: "
            )
            % minimum_duration
            + query
        )

    if selected is None:
        raise ProductionError(
            (
                "Pexels returned only portrait backgrounds used "
                "within the last %d Shorts. Query: "
            )
            % BACKGROUND_REUSE_WINDOW
            + query
        )

    selected_id = _normalize_pexels_id(
        selected.get(
            "id"
        )
    )

    if selected_id in used_ids:
        raise ProductionError(
            (
                "Duplicate Pexels background protection failed "
                "for ID "
            )
            + str(
                selected_id
            )
        )

    selected_duration = float(
        selected.get(
            "duration",
            0,
        )
        or 0
    )

    if selected_duration < minimum_duration:
        raise ProductionError(
            (
                "Selected background is too short: "
                "%.2fs < %.2fs"
            )
            % (
                selected_duration,
                minimum_duration,
            )
        )

    width = int(
        selected.get(
            "width",
            0,
        )
        or 0
    )

    height = int(
        selected.get(
            "height",
            0,
        )
        or 0
    )

    if (
        width <= 0
        or height <= 0
        or height <= width
    ):
        raise ProductionError(
            "Selected Pexels background is not portrait."
        )

    url = selected[
        "download"
    ]

    path = cache.path(
        "stock",
        url,
        ".mp4",
    )

    if not valid_media(
        path,
        "video",
    ):
        print(
            "[STEP] Downloading selected Pexels background",
            flush=True,
        )

        http.download(
            url,
            path,
        )

    if not valid_media(
        path,
        "video",
    ):
        raise ProductionError(
            "Selected Pexels background is not a readable video."
        )

    result = dict(
        selected
    )

    result[
        "local_path"
    ] = str(
        path
    )

    result[
        "search_query"
    ] = selected_query

    print(
        (
            "[OK] Background selected: "
            "%sx%s, %.1fs, Pexels ID %s"
        )
        % (
            selected.get(
                "width",
                0,
            ),
            selected.get(
                "height",
                0,
            ),
            selected_duration,
            selected.get(
                "id",
                "?",
            ),
        ),
        flush=True,
    )

    return result
