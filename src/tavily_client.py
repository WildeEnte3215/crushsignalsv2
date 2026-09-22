from urllib.parse import urlparse

from .utils import ProductionError


BASE = "https://api.tavily.com"


class Tavily:
    def __init__(
        self,
        settings,
        http,
        cache,
    ):
        self.s = settings
        self.http = http
        self.cache = cache

        key = settings.keys.get(
            "TAVILY_API_KEY",
            "",
        ).strip()

        if not key:
            raise ProductionError(
                "TAVILY_API_KEY is missing."
            )

        self.headers = {
            "Authorization":
            "Bearer " + key,
            "Content-Type":
            "application/json",
        }

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    @staticmethod
    def _clean_query(query):
        query = " ".join(
            str(query).split()
        ).strip()

        if not query:
            raise ProductionError(
                "Tavily search query is empty."
            )

        if len(query) > 400:
            query = query[:400].rstrip()

        return query

    @staticmethod
    def _validate_depth(depth):
        depth = str(
            depth
        ).strip().lower()

        if depth not in (
            "basic",
            "advanced",
        ):
            raise ProductionError(
                "Tavily search_depth must be "
                "'basic' or 'advanced'."
            )

        return depth

    @staticmethod
    def _validate_topic(topic):
        topic = str(
            topic
        ).strip().lower()

        if topic not in (
            "general",
            "news",
            "finance",
        ):
            raise ProductionError(
                "Tavily topic must be "
                "'general', 'news' or 'finance'."
            )

        return topic

    @staticmethod
    def _validate_time_range(
        value,
    ):
        if value is None:
            return None

        value = str(
            value
        ).strip().lower()

        allowed = (
            "day",
            "week",
            "month",
            "year",
            "d",
            "w",
            "m",
            "y",
        )

        if value not in allowed:
            raise ProductionError(
                "Invalid Tavily time_range: "
                + value
            )

        return value

    @staticmethod
    def _clean_domains(
        domains,
        maximum,
    ):
        if not domains:
            return []

        cleaned = []

        for domain in domains:
            domain = str(
                domain
            ).strip().lower()

            if not domain:
                continue

            domain = domain.removeprefix(
                "https://"
            ).removeprefix(
                "http://"
            )

            domain = domain.split(
                "/",
                1,
            )[0]

            if (
                domain
                and domain not in cleaned
            ):
                cleaned.append(
                    domain
                )

        return cleaned[
            :maximum
        ]

    # -----------------------------------------------------
    # NORMALIZATION
    # -----------------------------------------------------

    @staticmethod
    def _safe_url(url):
        url = str(
            url
            or ""
        ).strip()

        try:
            parsed = urlparse(
                url
            )
        except ValueError:
            return ""

        if (
            parsed.scheme
            not in (
                "http",
                "https",
            )
            or not parsed.netloc
        ):
            return ""

        return url

    @classmethod
    def _normalize_results(
        cls,
        response,
    ):
        normalized = []

        raw_results = response.get(
            "results",
            [],
        )

        if not isinstance(
            raw_results,
            list,
        ):
            raise ProductionError(
                "Tavily response has invalid "
                "'results' data."
            )

        for item in raw_results:
            if not isinstance(
                item,
                dict,
            ):
                continue

            url = cls._safe_url(
                item.get(
                    "url"
                )
            )

            if not url:
                continue

            title = " ".join(
                str(
                    item.get(
                        "title",
                        "",
                    )
                ).split()
            ).strip()

            if not title:
                title = url

            content = str(
                item.get(
                    "content",
                    "",
                )
                or ""
            ).strip()

            if len(content) > 6000:
                content = (
                    content[
                        :6000
                    ].rstrip()
                    + "..."
                )

            score = item.get(
                "score"
            )

            try:
                score = (
                    float(score)
                    if score is not None
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                score = None

            normalized.append(
                {
                    "title":
                    title,

                    "url":
                    url,

                    "content":
                    content,

                    "score":
                    score,
                }
            )

        return normalized

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    def search(
        self,
        query,
        depth="basic",
        max_results=6,
        topic="general",
        time_range=None,
        include_domains=None,
        exclude_domains=None,
    ):
        query = self._clean_query(
            query
        )

        depth = self._validate_depth(
            depth
        )

        topic = self._validate_topic(
            topic
        )

        time_range = (
            self._validate_time_range(
                time_range
            )
        )

        if (
            not isinstance(
                max_results,
                int,
            )
            or isinstance(
                max_results,
                bool,
            )
            or not 1
            <= max_results
            <= 20
        ):
            raise ProductionError(
                "Tavily max_results must "
                "be an integer from 1 to 20."
            )

        include_domains = (
            self._clean_domains(
                include_domains,
                300,
            )
        )

        exclude_domains = (
            self._clean_domains(
                exclude_domains,
                150,
            )
        )

        payload = {
            "query":
            query,

            "auto_parameters":
            False,

            "topic":
            topic,

            "search_depth":
            depth,

            "max_results":
            max_results,

            "include_answer":
            False,

            "include_raw_content":
            False,

            "include_images":
            False,
        }

        if depth == "advanced":
            payload[
                "chunks_per_source"
            ] = 3

        if time_range:
            payload[
                "time_range"
            ] = time_range

        if include_domains:
            payload[
                "include_domains"
            ] = include_domains

        if exclude_domains:
            payload[
                "exclude_domains"
            ] = exclude_domains

        cache_key = {
            "provider":
            "tavily",

            "endpoint":
            "search",

            "payload":
            payload,
        }

        hit = self.cache.get(
            "tavily",
            cache_key,
        )

        if hit is not None:
            return hit

        response = self.http.request(
            "POST",
            BASE + "/search",
            self.headers,
            payload,
        )

        if not isinstance(
            response,
            dict,
        ):
            raise ProductionError(
                "Tavily returned an invalid response."
            )

        results = self._normalize_results(
            response
        )

        if not results:
            raise ProductionError(
                "Tavily search returned no usable "
                "web results for: "
                + query
            )

        usage = response.get(
            "usage",
            {},
        )

        credits = None

        if isinstance(
            usage,
            dict,
        ):
            credits = usage.get(
                "credits"
            )

        normalized = {
            "query":
            str(
                response.get(
                    "query",
                    query,
                )
            ),

            "results":
            results,

            "credits":
            credits,

            "request_id":
            response.get(
                "request_id"
            ),

            "response_time":
            response.get(
                "response_time"
            ),
        }

        self.cache.put(
            "tavily",
            cache_key,
            normalized,
        )

        return normalized

    # -----------------------------------------------------
    # CONVENIENCE SEARCHES
    # -----------------------------------------------------

    def research_search(
        self,
        query,
        max_results=8,
        topic="general",
        time_range=None,
    ):
        return self.search(
            query=query,
            depth="advanced",
            max_results=max_results,
            topic=topic,
            time_range=time_range,
        )

    def fact_search(
        self,
        query,
        max_results=6,
        topic="general",
        time_range=None,
    ):
        return self.search(
            query=query,
            depth="basic",
            max_results=max_results,
            topic=topic,
            time_range=time_range,
        )

    # -----------------------------------------------------
    # SOURCE HELPERS
    # -----------------------------------------------------

    @staticmethod
    def sources(response):
        found = {}

        for item in response.get(
            "results",
            [],
        ):
            url = item.get(
                "url"
            )

            if not url:
                continue

            found[
                url
            ] = item.get(
                "title",
                url,
            )

        return found

    @staticmethod
    def format_results(
        response,
    ):
        blocks = []

        for index, item in enumerate(
            response.get(
                "results",
                [],
            ),
            start=1,
        ):
            title = item.get(
                "title",
                ""
            )

            url = item.get(
                "url",
                ""
            )

            content = item.get(
                "content",
                ""
            )

            blocks.append(
                "\n".join(
                    [
                        (
                            "[SOURCE %d]"
                            % index
                        ),
                        (
                            "Title: "
                            + title
                        ),
                        (
                            "URL: "
                            + url
                        ),
                        (
                            "Evidence: "
                            + (
                                content
                                or "(no snippet)"
                            )
                        ),
                    ]
                )
            )

        if not blocks:
            raise ProductionError(
                "Cannot format empty Tavily results."
            )

        return "\n\n".join(
            blocks
        )

    def bundle(
        self,
        query,
        depth="advanced",
        max_results=8,
        topic="general",
        time_range=None,
    ):
        response = self.search(
            query=query,
            depth=depth,
            max_results=max_results,
            topic=topic,
            time_range=time_range,
        )

        return {
            "text":
            self.format_results(
                response
            ),

            "sources":
            self.sources(
                response
            ),

            "results":
            response[
                "results"
            ],

            "credits":
            response.get(
                "credits"
            ),

            "request_id":
            response.get(
                "request_id"
            ),
        }