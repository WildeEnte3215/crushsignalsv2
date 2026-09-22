from urllib.parse import urlencode


class PexelsProvider:
    name = "Pexels"
    home = "https://www.pexels.com"
    license_url = (
        "https://www.pexels.com/license/"
    )

    def __init__(
        self,
        settings,
        http,
        cache,
    ):
        self.s = settings
        self.http = http
        self.cache = cache

    def search(
        self,
        query,
    ):
        params = {
            "query": query,
            "per_page": 30,
            "locale": "en-US",
        }

        data = self.cache.get(
            "pexels",
            params,
            86400,
        )

        if data is None:
            data = self.http.request(
                "GET",
                (
                    "https://api.pexels.com/"
                    "v1/videos/search?"
                    + urlencode(
                        params
                    )
                ),
                {
                    "Authorization": (
                        self.s.keys[
                            "PEXELS_API_KEY"
                        ]
                    )
                },
            )

            self.cache.put(
                "pexels",
                params,
                data,
            )

        results = []

        for item in data.get(
            "videos",
            [],
        ):
            files = [
                video
                for video
                in item.get(
                    "video_files",
                    [],
                )
                if (
                    video.get(
                        "file_type"
                    )
                    == "video/mp4"
                    and video.get(
                        "width"
                    )
                    and video.get(
                        "height"
                    )
                    and video.get(
                        "link"
                    )
                )
            ]

            if not files:
                continue

            # Smaller preview for cheaper/faster
            # visual evaluation.
            preview = min(
                files,
                key=lambda video: abs(
                    max(
                        video[
                            "width"
                        ],
                        video[
                            "height"
                        ],
                    )
                    - 960
                ),
            )

            # Prefer a full-resolution file
            # around 1080 short-edge resolution.
            full = min(
                files,
                key=lambda video: (
                    abs(
                        min(
                            video[
                                "width"
                            ],
                            video[
                                "height"
                            ],
                        )
                        - 1080
                    ),
                    -min(
                        video[
                            "width"
                        ],
                        video[
                            "height"
                        ],
                    ),
                ),
            )

            results.append(
                {
                    "provider": (
                        self.name
                    ),
                    "id": str(
                        item[
                            "id"
                        ]
                    ),
                    "url": (
                        item[
                            "url"
                        ]
                    ),
                    "author": (
                        item.get(
                            "user",
                            {},
                        ).get(
                            "name",
                            "",
                        )
                    ),
                    "license": (
                        self.license_url
                    ),
                    "provider_url": (
                        self.home
                    ),
                    "preview": (
                        preview[
                            "link"
                        ]
                    ),
                    "download": (
                        full[
                            "link"
                        ]
                    ),
                    "width": (
                        full[
                            "width"
                        ]
                    ),
                    "height": (
                        full[
                            "height"
                        ]
                    ),
                    "duration": (
                        item.get(
                            "duration",
                            0,
                        )
                    ),
                }
            )

        return results