import html
import math
import re
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from .stock.pexels import PexelsProvider
from .stock.fallback import PixabayProvider
from .utils import (
    ProductionError,
    command,
    probe,
    valid_media,
    save,
    atomic,
)


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
    "would",
    "you",
}


def clamp(value, low=0.0, high=1.0):
    return max(
        low,
        min(
            high,
            float(value),
        ),
    )


def frame(
    path,
    seconds,
    target,
):
    command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            str(
                max(
                    0.0,
                    float(seconds),
                )
            ),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=960:-2",
            "-threads",
            "1",
            str(target),
        ]
    )

    target = Path(
        target
    )

    if not target.is_file():
        raise ProductionError(
            "Frame extraction returned no image; "
            "trying another candidate."
        )

    return target


def local_frame_quality(
    image_path,
):
    """
    Cheap local visual-quality estimate.

    This deliberately does NOT try to understand
    scene semantics. Pexels search order handles
    relevance; this only rejects obviously poor
    frames and prefers clearer ones.
    """

    try:
        with Image.open(
            image_path
        ) as image:
            gray = (
                image
                .convert("L")
                .resize(
                    (
                        320,
                        320,
                    )
                )
            )

            stats = ImageStat.Stat(
                gray
            )

            brightness = float(
                stats.mean[0]
            )

            contrast = float(
                stats.stddev[0]
            )

            edges = gray.filter(
                ImageFilter.FIND_EDGES
            )

            edge_strength = float(
                ImageStat.Stat(
                    edges
                ).mean[0]
            )

    except Exception as e:
        raise ProductionError(
            "Could not inspect local preview frame: "
            + str(e)
        ) from e

    # Avoid extremely black/white frames.
    if brightness < 12:
        brightness_score = 0.05
    elif brightness < 35:
        brightness_score = 0.45
    elif brightness > 245:
        brightness_score = 0.10
    elif brightness > 225:
        brightness_score = 0.55
    else:
        brightness_score = 1.0

    contrast_score = clamp(
        contrast / 55.0
    )

    detail_score = clamp(
        edge_strength / 28.0
    )

    quality = (
        0.35
        * brightness_score
        + 0.30
        * contrast_score
        + 0.35
        * detail_score
    )

    return {
        "quality":
        clamp(
            quality
        ),

        "brightness":
        round(
            brightness,
            2,
        ),

        "contrast":
        round(
            contrast,
            2,
        ),

        "detail":
        round(
            edge_strength,
            2,
        ),
    }


class Ranker:
    """
    COST-OPTIMIZED VISUAL RANKER

    Normal visual selection uses ZERO AI requests.

    Relevance:
        stock provider result order + query order

    Suitability:
        aspect ratio + resolution + duration

    Visual sanity:
        local FFmpeg frame extraction + Pillow metrics

    The 'ai' parameter is kept only so pipeline.py
    remains backward compatible.
    """

    def __init__(
        self,
        settings,
        http,
        cache,
        ai,
    ):
        self.s = settings
        self.http = http
        self.cache = cache

        # Intentionally unused in the normal ranking path.
        # Keep it only for constructor compatibility.
        self.ai = ai

        self.providers = [
            PexelsProvider(
                settings,
                http,
                cache,
            )
        ]

        if settings.keys[
            "PIXABAY_API_KEY"
        ]:
            self.providers.append(
                PixabayProvider(
                    settings,
                    http,
                    cache,
                )
            )

    # -----------------------------------------------------
    # DOWNLOAD
    # -----------------------------------------------------

    def downloaded(
        self,
        candidate,
        preview=False,
    ):
        url = candidate[
            "preview"
            if preview
            else "download"
        ]

        path = self.cache.path(
            "stock",
            url,
            ".mp4",
        )

        if not valid_media(
            path,
            "video",
        ):
            self.http.download(
                url,
                path,
            )

        if not valid_media(
            path,
            "video",
        ):
            raise ProductionError(
                "Stock download is not a readable video."
            )

        return path

    # -----------------------------------------------------
    # LOCAL QUERY FALLBACK
    # -----------------------------------------------------

    @staticmethod
    def keywords(
        text,
        maximum=5,
    ):
        words = re.findall(
            r"[A-Za-z0-9]+",
            str(
                text
                or ""
            ).lower(),
        )

        result = []

        for word in words:
            if (
                len(word) < 3
                or word in STOPWORDS
                or word in result
            ):
                continue

            result.append(
                word
            )

            if len(
                result
            ) >= maximum:
                break

        return result

    def local_queries(
        self,
        scene,
        attempt,
    ):
        """
        No AI query rewrite.

        attempt 0:
            use script-generated stock queries

        later attempts:
            create short local fallbacks from the
            visual goal / overlay target / narration
        """

        if attempt == 0:
            return [
                str(
                    query
                ).strip()
                for query
                in scene.search_queries
                if str(
                    query
                ).strip()
            ][
                :3
            ]

        candidates = []

        target = str(
            scene.edit.target
            or ""
        ).strip()

        if (
            target
            and target.lower()
            not in (
                "none",
                "n/a",
            )
        ):
            words = self.keywords(
                target,
                4,
            )

            if words:
                candidates.append(
                    " ".join(
                        words
                    )
                )

        goal_words = self.keywords(
            scene.visual_goal,
            5,
        )

        if goal_words:
            candidates.append(
                " ".join(
                    goal_words[
                        :4
                    ]
                )
            )

        narration_words = self.keywords(
            scene.narration,
            5,
        )

        if narration_words:
            candidates.append(
                " ".join(
                    narration_words[
                        :4
                    ]
                )
            )

        # On later attempts, get broader rather than
        # spending another model request.
        if attempt >= 2:
            broader = (
                goal_words[
                    :2
                ]
                or narration_words[
                    :2
                ]
            )

            if broader:
                candidates.append(
                    " ".join(
                        broader
                    )
                )

        result = []
        seen = set()

        for query in candidates:
            query = " ".join(
                query.split()
            ).strip()

            key = query.lower()

            if (
                query
                and key not in seen
            ):
                seen.add(
                    key
                )

                result.append(
                    query
                )

        return result[
            :3
        ]

    # -----------------------------------------------------
    # METADATA SCORING
    # -----------------------------------------------------

    @staticmethod
    def vertical_score(
        candidate,
    ):
        width = max(
            1.0,
            float(
                candidate.get(
                    "width",
                    1,
                )
            ),
        )

        height = max(
            1.0,
            float(
                candidate.get(
                    "height",
                    1,
                )
            ),
        )

        aspect = (
            width
            / height
        )

        target = (
            1080.0
            / 1920.0
        )

        distance = abs(
            math.log(
                max(
                    0.01,
                    aspect
                    / target,
                )
            )
        )

        return clamp(
            1.0
            - distance
            / 1.75
        )

    @staticmethod
    def resolution_score(
        candidate,
    ):
        width = max(
            1.0,
            float(
                candidate.get(
                    "width",
                    1,
                )
            ),
        )

        height = max(
            1.0,
            float(
                candidate.get(
                    "height",
                    1,
                )
            ),
        )

        short_side = min(
            width,
            height,
        )

        pixels = (
            width
            * height
        )

        side_score = clamp(
            short_side
            / 1080.0
        )

        pixel_score = clamp(
            pixels
            / (
                1920.0
                * 1080.0
            )
        )

        return (
            0.55
            * side_score
            + 0.45
            * pixel_score
        )

    @staticmethod
    def duration_score(
        candidate,
    ):
        try:
            duration = float(
                candidate.get(
                    "duration",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            duration = 0.0

        if duration >= 4:
            return 1.0

        if duration >= 3:
            return 0.90

        if duration >= 2:
            return 0.70

        if duration >= 1:
            return 0.40

        return 0.05

    @staticmethod
    def relevance_score(
        candidate,
    ):
        query_rank = int(
            candidate.get(
                "_query_rank",
                0,
            )
        )

        result_rank = int(
            candidate.get(
                "_result_rank",
                0,
            )
        )

        attempt = int(
            candidate.get(
                "_search_attempt",
                0,
            )
        )

        score = (
            1.0
            - 0.07
            * query_rank
            - 0.035
            * result_rank
            - 0.08
            * attempt
        )

        return clamp(
            score,
            0.25,
            1.0,
        )

    def metadata_score(
        self,
        candidate,
    ):
        relevance = (
            self.relevance_score(
                candidate
            )
        )

        vertical = (
            self.vertical_score(
                candidate
            )
        )

        resolution = (
            self.resolution_score(
                candidate
            )
        )

        duration = (
            self.duration_score(
                candidate
            )
        )

        total = (
            0.46
            * relevance
            + 0.26
            * vertical
            + 0.20
            * resolution
            + 0.08
            * duration
        )

        return {
            "score":
            clamp(
                total
            ),

            "relevance":
            relevance,

            "vertical":
            vertical,

            "resolution":
            resolution,

            "duration":
            duration,
        }

    # -----------------------------------------------------
    # LOCAL PREVIEW CHECK
    # -----------------------------------------------------

    def preview_score(
        self,
        candidate,
        folder,
        provider_name,
    ):
        preview = self.downloaded(
            candidate,
            True,
        )

        duration = float(
            probe(
                preview
            )[
                "format"
            ][
                "duration"
            ]
        )

        seconds = min(
            max(
                0.05,
                duration
                * 0.5,
            ),
            max(
                0.05,
                duration
                - 0.10,
            ),
        )

        image = frame(
            preview,
            seconds,
            folder
            / (
                "preview_%s_%s.jpg"
                % (
                    provider_name,
                    candidate[
                        "id"
                    ],
                )
            ),
        )

        metrics = (
            local_frame_quality(
                image
            )
        )

        metadata = (
            self.metadata_score(
                candidate
            )
        )

        score = (
            0.84
            * metadata[
                "score"
            ]
            + 0.16
            * metrics[
                "quality"
            ]
        )

        assessment = {
            "relevance":
            round(
                metadata[
                    "relevance"
                ],
                4,
            ),

            "visibility":
            round(
                (
                    0.55
                    * metadata[
                        "vertical"
                    ]
                    + 0.45
                    * metrics[
                        "quality"
                    ]
                ),
                4,
            ),

            "vertical":
            round(
                metadata[
                    "vertical"
                ],
                4,
            ),

            "quality":
            round(
                (
                    0.55
                    * metadata[
                        "resolution"
                    ]
                    + 0.45
                    * metrics[
                        "quality"
                    ]
                ),
                4,
            ),

            "reject":
            bool(
                metadata[
                    "resolution"
                ]
                < 0.22
                or metadata[
                    "duration"
                ]
                < 0.35
                or metrics[
                    "quality"
                ]
                < 0.18
            ),

            "reason":
            (
                "Local metadata + frame-quality ranking; "
                "no AI vision request used."
            ),

            # Keep the exact Assessment interface expected by
            # render.py / overlays.py without inventing visual
            # knowledge we no longer obtain from Gemini Vision.
            #
            # Center-focused crop is safe for ordinary stock.
            "crop":
            "focus",

            "focus_x":
            0.5,

            "focus_y":
            0.5,

            # The local ranker cannot truthfully confirm a semantic
            # annotation target. Mark it as NOT verified so arrows /
            # circles are skipped instead of being drawn at a fake
            # position.
            "target_visible":
            False,

            "target_confidence":
            0.0,

            # Schema-compatible neutral defaults. They are ignored
            # while target_visible is False.
            "target_x":
            0.5,

            "target_y":
            0.5,

            "target_radius":
            0.08,

            "local_frame_metrics":
            metrics,
        }

        return (
            clamp(
                score
            ),
            assessment,
            image,
        )

    # -----------------------------------------------------
    # BEST EXACT FRAME
    # -----------------------------------------------------

    def exact_frame(
        self,
        candidate,
        path,
        folder,
        provider_name,
    ):
        duration = float(
            probe(
                path
            )[
                "format"
            ][
                "duration"
            ]
        )

        fractions = [
            0.20,
            0.42,
            0.62,
            0.82,
        ]

        options = []

        for n, fraction in enumerate(
            fractions
        ):
            seconds = min(
                max(
                    0.05,
                    duration
                    * fraction,
                ),
                max(
                    0.05,
                    duration
                    - 0.10,
                ),
            )

            image = frame(
                path,
                seconds,
                folder
                / (
                    "exact_%s_%s_%02d.jpg"
                    % (
                        provider_name,
                        candidate[
                            "id"
                        ],
                        n,
                    )
                ),
            )

            metrics = (
                local_frame_quality(
                    image
                )
            )

            options.append(
                (
                    metrics[
                        "quality"
                    ],
                    seconds,
                    image,
                    metrics,
                )
            )

        if not options:
            raise ProductionError(
                "No usable frame could be extracted "
                "from selected stock video."
            )

        return max(
            options,
            key=lambda item: item[
                0
            ],
        )

    # -----------------------------------------------------
    # SERIALIZATION HELPERS
    # -----------------------------------------------------

    @staticmethod
    def clean_candidate(
        candidate,
    ):
        return {
            key: value
            for key, value
            in candidate.items()
            if not str(
                key
            ).startswith(
                "_"
            )
        }

    @staticmethod
    def candidate_key(
        provider_name,
        candidate,
    ):
        return (
            str(
                provider_name
            ),
            str(
                candidate.get(
                    "id",
                    "",
                )
            ),
        )

    # -----------------------------------------------------
    # DEBUG OUTPUT
    # -----------------------------------------------------

    @staticmethod
    def save_html(
        folder,
        records,
    ):
        links = []

        for record in records:
            candidate_url = html.escape(
                str(
                    record.get(
                        "url",
                        "",
                    )
                ),
                quote=True,
            )

            provider = html.escape(
                str(
                    record.get(
                        "provider",
                        "",
                    )
                )
            )

            author = html.escape(
                str(
                    record.get(
                        "author",
                        "",
                    )
                )
            )

            assessment = record.get(
                "assessment",
                {},
            )

            links.append(
                (
                    '<p><a href="%s">%s - %s</a>'
                    ' | local score %.2f'
                    ' | search relevance %.2f'
                    ' | vertical %.2f'
                    ' | quality %.2f'
                    ' | reject %s'
                    '</p>'
                )
                % (
                    candidate_url,
                    provider,
                    author,
                    float(
                        record.get(
                            "score",
                            0,
                        )
                    ),
                    float(
                        assessment.get(
                            "relevance",
                            0,
                        )
                    ),
                    float(
                        assessment.get(
                            "vertical",
                            0,
                        )
                    ),
                    float(
                        assessment.get(
                            "quality",
                            0,
                        )
                    ),
                    bool(
                        assessment.get(
                            "reject",
                            False,
                        )
                    ),
                )
            )

        atomic(
            folder
            / "candidates.html",
            (
                '<!doctype html>'
                '<meta charset="utf-8">'
                '<h1>Footage selection</h1>'
                '<p>Cost-optimized local ranking. '
                'No AI vision requests used.</p>'
                '<p>Videos provided by '
                '<a href="https://www.pexels.com">'
                'Pexels</a> and optionally '
                '<a href="https://pixabay.com">'
                'Pixabay</a>.</p>'
                + "".join(
                    links
                )
            ),
        )

    # -----------------------------------------------------
    # SELECTION
    # -----------------------------------------------------

    def select(
        self,
        scene,
        folder,
    ):
        folder = Path(
            folder
        )

        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        errors = []
        records = []
        used_queries = set()

        planned_diagram = bool(
            scene.prefer_diagram
        )

        for provider in self.providers:
            for attempt in range(
                self.s.video[
                    "query_attempts"
                ]
            ):
                queries = (
                    self.local_queries(
                        scene,
                        attempt,
                    )
                )

                current_queries = []

                for query in queries:
                    query = " ".join(
                        str(
                            query
                        ).split()
                    ).strip()

                    if not query:
                        continue

                    key = query.lower()

                    if key in used_queries:
                        continue

                    used_queries.add(
                        key
                    )

                    current_queries.append(
                        query
                    )

                if not current_queries:
                    continue

                candidates = {}

                try:
                    for query_rank, query in enumerate(
                        current_queries[
                            :3
                        ]
                    ):
                        results = provider.search(
                            query
                        )

                        for result_rank, raw in enumerate(
                            results
                        ):
                            candidate = dict(
                                raw
                            )

                            candidate[
                                "_query_rank"
                            ] = query_rank

                            candidate[
                                "_result_rank"
                            ] = result_rank

                            candidate[
                                "_search_attempt"
                            ] = attempt

                            key = self.candidate_key(
                                provider.name,
                                candidate,
                            )

                            existing = candidates.get(
                                key
                            )

                            if existing is None:
                                candidates[
                                    key
                                ] = candidate

                            else:
                                if (
                                    self.metadata_score(
                                        candidate
                                    )[
                                        "score"
                                    ]
                                    > self.metadata_score(
                                        existing
                                    )[
                                        "score"
                                    ]
                                ):
                                    candidates[
                                        key
                                    ] = candidate

                except ProductionError as e:
                    errors.append(
                        str(e)
                    )

                    continue

                if not candidates:
                    continue

                short = sorted(
                    candidates.values(),
                    key=lambda candidate: (
                        self.metadata_score(
                            candidate
                        )[
                            "score"
                        ]
                    ),
                    reverse=True,
                )

                # Only inspect a few previews locally.
                # No need to download/analyze six or thirty clips.
                preview_limit = min(
                    4,
                    max(
                        2,
                        int(
                            self.s.video[
                                "stock_candidates"
                            ]
                        ),
                    ),
                )

                ranked = []

                for candidate in short[
                    :preview_limit
                ]:
                    try:
                        (
                            local_score,
                            assessment,
                            preview_frame,
                        ) = self.preview_score(
                            candidate,
                            folder,
                            provider.name,
                        )

                        record = dict(
                            self.clean_candidate(
                                candidate
                            ),
                            assessment=assessment,
                            score=local_score,
                            search_attempt=attempt
                            + 1,
                            preview_frame=str(
                                preview_frame
                            ),
                        )

                        records.append(
                            record
                        )

                        if not assessment[
                            "reject"
                        ]:
                            ranked.append(
                                (
                                    local_score,
                                    candidate,
                                    assessment,
                                )
                            )

                    except ProductionError as e:
                        errors.append(
                            str(e)
                        )

                save(
                    folder
                    / "candidates.json",
                    {
                        "ranking_mode":
                        "local_zero_ai",

                        "planned_diagram":
                        planned_diagram,

                        "queries_used":
                        sorted(
                            used_queries
                        ),

                        "candidates":
                        records,

                        "errors":
                        errors,
                    },
                )

                self.save_html(
                    folder,
                    records,
                )

                for (
                    preliminary_score,
                    candidate,
                    preliminary_assessment,
                ) in sorted(
                    ranked,
                    key=lambda item: item[
                        0
                    ],
                    reverse=True,
                ):
                    try:
                        path = self.downloaded(
                            candidate,
                            False,
                        )

                        (
                            exact_quality,
                            seconds,
                            exact_image,
                            exact_metrics,
                        ) = self.exact_frame(
                            candidate,
                            path,
                            folder,
                            provider.name,
                        )

                        exact_score = clamp(
                            0.88
                            * preliminary_score
                            + 0.12
                            * exact_quality
                        )

                        assessment = dict(
                            preliminary_assessment
                        )

                        assessment[
                            "quality"
                        ] = round(
                            clamp(
                                0.75
                                * float(
                                    assessment[
                                        "quality"
                                    ]
                                )
                                + 0.25
                                * exact_quality
                            ),
                            4,
                        )

                        assessment[
                            "exact_frame_metrics"
                        ] = exact_metrics

                        assessment[
                            "reason"
                        ] = (
                            "Selected with Pexels/Pixabay "
                            "search order, metadata and local "
                            "frame-quality checks. Zero AI "
                            "vision requests."
                        )

                        return {
                            "kind":
                            "stock",

                            "path":
                            str(
                                path
                            ),

                            "frame":
                            str(
                                exact_image
                            ),

                            "offset":
                            seconds,

                            "candidate":
                            self.clean_candidate(
                                candidate
                            ),

                            "assessment":
                            assessment,

                            "preliminary_score":
                            preliminary_score,

                            "exact_score":
                            exact_score,

                            "ranking_mode":
                            "local_zero_ai",
                        }

                    except ProductionError as e:
                        errors.append(
                            str(e)
                        )

        save(
            folder
            / "candidates.json",
            {
                "ranking_mode":
                "local_zero_ai",

                "planned_diagram":
                planned_diagram,

                "queries_used":
                sorted(
                    used_queries
                ),

                "candidates":
                records,

                "errors":
                errors,
            },
        )

        self.save_html(
            folder,
            records,
        )

        return {
            "kind":
            "diagram",

            "reason":
            (
                "Planned schematic and no suitable stock found"
                if planned_diagram
                else (
                    "No sufficiently usable "
                    "downloadable stock found"
                )
            ),

            "errors":
            errors,

            "ranking_mode":
            "local_zero_ai",
        }
