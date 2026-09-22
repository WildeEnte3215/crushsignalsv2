import base64
from pathlib import Path

from pydantic import ValidationError

from .utils import ProductionError


BASE = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models"
)


class Gemini:
    def __init__(
        self,
        settings,
        http,
        cache,
        budget,
    ):
        self.s = settings
        self.http = http
        self.cache = cache
        self.budget = budget

        self.headers = {
            "x-goog-api-key": (
                settings.keys[
                    "GEMINI_API_KEY"
                ]
            ),
            "Content-Type":
            "application/json",
        }

    # -----------------------------------------------------
    # RESPONSE HELPERS
    # -----------------------------------------------------

    @staticmethod
    def output(response):
        candidates = response.get(
            "candidates",
            [],
        )

        if not candidates:
            prompt_feedback = response.get(
                "promptFeedback",
                {},
            )

            raise ProductionError(
                "Gemini response contains no candidates. "
                + str(
                    prompt_feedback
                )
            )

        texts = []

        for candidate in candidates:
            content = candidate.get(
                "content",
                {},
            )

            for part in content.get(
                "parts",
                [],
            ):
                text = part.get(
                    "text"
                )

                if text:
                    texts.append(
                        text
                    )

        if not texts:
            finish_reasons = [
                candidate.get(
                    "finishReason"
                )
                for candidate
                in candidates
            ]

            raise ProductionError(
                "Gemini response contains no text. "
                "Finish reasons: "
                + str(
                    finish_reasons
                )
            )

        return "\n".join(
            texts
        )

    @staticmethod
    def sources(response):
        """
        Extract Google Search grounding sources.

        Returns:
            {
                "URL": "title",
                ...
            }
        """

        found = {}

        for candidate in response.get(
            "candidates",
            [],
        ):
            metadata = candidate.get(
                "groundingMetadata",
                {},
            )

            for chunk in metadata.get(
                "groundingChunks",
                [],
            ):
                web = chunk.get(
                    "web",
                    {},
                )

                uri = web.get(
                    "uri"
                )

                if not uri:
                    continue

                title = web.get(
                    "title",
                    uri,
                )

                found[
                    uri
                ] = title

        return found

    # -----------------------------------------------------
    # GENERIC API CALL
    # -----------------------------------------------------

    def call(
        self,
        payload,
        model=None,
    ):
        model = (
            model
            or self.s.video[
                "research_model"
            ]
        )

        cache_key = {
            "provider":
            "gemini",

            "model":
            model,

            "payload":
            payload,
        }

        hit = self.cache.get(
            "gemini",
            cache_key,
        )

        if hit is not None:
            self.output(
                hit
            )

            return hit

        url = (
            BASE
            + "/"
            + model
            + ":generateContent"
        )

        response = self.http.request(
            "POST",
            url,
            self.headers,
            payload,
        )

        self.output(
            response
        )

        self.cache.put(
            "gemini",
            cache_key,
            response,
        )

        return response

    # -----------------------------------------------------
    # JSON SCHEMA CLEANUP
    # -----------------------------------------------------

    @staticmethod
    def clean_schema(value):
        """
        Gemini supports a useful subset of JSON Schema.

        Pydantic adds validation keywords that are not
        necessary for the API request. Local Pydantic
        validation still checks the final response.
        """

        allowed = {
            "$id",
            "$defs",
            "$ref",
            "$anchor",
            "type",
            "format",
            "title",
            "description",
            "enum",
            "const",
            "items",
            "prefixItems",
            "minItems",
            "maxItems",
            "minimum",
            "maximum",
            "anyOf",
            "oneOf",
            "allOf",
            "properties",
            "additionalProperties",
            "required",
        }

        if isinstance(
            value,
            list,
        ):
            return [
                Gemini.clean_schema(
                    item
                )
                for item
                in value
            ]

        if not isinstance(
            value,
            dict,
        ):
            return value

        cleaned = {}

        for key, item in value.items():
            if key not in allowed:
                continue

            if key == "properties":
                cleaned[
                    key
                ] = {
                    name:
                    Gemini.clean_schema(
                        schema
                    )
                    for name, schema
                    in item.items()
                }

            elif key == "$defs":
                cleaned[
                    key
                ] = {
                    name:
                    Gemini.clean_schema(
                        schema
                    )
                    for name, schema
                    in item.items()
                }

            else:
                cleaned[
                    key
                ] = Gemini.clean_schema(
                    item
                )

        return cleaned

    # -----------------------------------------------------
    # OUTPUT TOKEN LIMITS
    # -----------------------------------------------------

    @staticmethod
    def schema_output_limit(
        schema,
    ):
        name = schema.__name__

        limits = {
            "Assessment": 700,
            "Queries": 400,
            "Topic": 300,
            "Review": 900,
            "Verdict": 1400,
            "Research": 4500,
            "Plan": 4500,
        }

        return limits.get(
            name,
            2500,
        )

    # -----------------------------------------------------
    # IMAGE MIME TYPE
    # -----------------------------------------------------

    @staticmethod
    def image_mime(path):
        suffix = (
            Path(path)
            .suffix
            .lower()
        )

        return {
            ".jpg":
            "image/jpeg",

            ".jpeg":
            "image/jpeg",

            ".png":
            "image/png",

            ".webp":
            "image/webp",
        }.get(
            suffix,
            "image/jpeg",
        )

    # -----------------------------------------------------
    # IMAGE PART
    # -----------------------------------------------------

    @classmethod
    def image_part(
        cls,
        path,
    ):
        path = Path(
            path
        )

        if not path.is_file():
            raise ProductionError(
                "Vision image missing: "
                + str(
                    path
                )
            )

        return {
            "inline_data": {
                "mime_type":
                cls.image_mime(
                    path
                ),

                "data":
                base64.b64encode(
                    path.read_bytes()
                ).decode(
                    "ascii"
                ),
            }
        }

    # -----------------------------------------------------
    # STRUCTURED OUTPUT
    # -----------------------------------------------------

    def structured(
        self,
        prompt,
        schema,
        vision=None,
        model=None,
    ):
        model = (
            model
            or self.s.video[
                "research_model"
            ]
        )

        parts = [
            {
                "text":
                str(
                    prompt
                )
            }
        ]

        for path in (
            vision
            or []
        ):
            parts.append(
                self.image_part(
                    path
                )
            )

        schema_json = (
            self.clean_schema(
                schema.model_json_schema()
            )
        )

        payload = {
            "contents": [
                {
                    "role":
                    "user",

                    "parts":
                    parts,
                }
            ],

            "generationConfig": {
                "responseMimeType":
                "application/json",

                "responseJsonSchema":
                schema_json,

                "maxOutputTokens":
                self.schema_output_limit(
                    schema
                ),

                # Gemini 3.x uses thinkingLevel.
                # JSON extraction and visual ranking
                # normally need almost no reasoning.
                "thinkingConfig": {
                    "thinkingLevel":
                    "minimal"
                },

                "temperature":
                0.2,
            },
        }

        validated_key = {
            "provider":
            "gemini",

            "model":
            model,

            "schema":
            schema.__name__,

            "payload":
            payload,
        }

        hit = self.cache.get(
            "gemini_validated",
            validated_key,
        )

        if hit is not None:
            return schema.model_validate(
                hit
            )

        last_error = None
        invalid_raw = None

        for attempt in range(
            2
        ):
            response = self.call(
                payload,
                model,
            )

            raw = self.output(
                response
            )

            try:
                result = (
                    schema.model_validate_json(
                        raw
                    )
                )

                self.cache.put(
                    "gemini_validated",
                    validated_key,
                    result.model_dump(),
                )

                return result

            except (
                ValidationError,
                ValueError,
            ) as e:
                last_error = e
                invalid_raw = raw

                if attempt:
                    break

                repair_parts = [
                    {
                        "text": (
                            "Your previous JSON did not "
                            "satisfy the required schema.\n\n"
                            "Return ONLY corrected JSON.\n"
                            "Do not add new facts.\n"
                            "Do not change factual meaning.\n\n"
                            "ORIGINAL TASK:\n"
                            + str(
                                prompt
                            )
                            + "\n\n"
                            "INVALID OUTPUT:\n"
                            + invalid_raw
                        )
                    }
                ]

                for path in (
                    vision
                    or []
                ):
                    repair_parts.append(
                        self.image_part(
                            path
                        )
                    )

                payload = {
                    "contents": [
                        {
                            "role":
                            "user",

                            "parts":
                            repair_parts,
                        }
                    ],

                    "generationConfig": {
                        "responseMimeType":
                        "application/json",

                        "responseJsonSchema":
                        schema_json,

                        "maxOutputTokens":
                        self.schema_output_limit(
                            schema
                        ),

                        "thinkingConfig": {
                            "thinkingLevel":
                            "minimal"
                        },

                        "temperature":
                        0.1,
                    },
                }

        raise ProductionError(
            "Gemini structured output invalid "
            "after one repair: "
            + str(
                last_error
            )
        )

    # -----------------------------------------------------
    # GOOGLE SEARCH RESEARCH
    # -----------------------------------------------------

    def research(
        self,
        prompt,
    ):
        model = (
            self.s.video[
                "research_model"
            ]
        )

        base_prompt = (
            str(
                prompt
            )
            + "\n\n"
            + (
                "Use Google Search for this task. "
                "Ground factual claims in the search "
                "results. Prefer primary, official, "
                "academic, engineering, manufacturer "
                "or directly authoritative sources. "
                "Do not rely on social-media posts, "
                "SEO summaries or unsourced claims "
                "when stronger sources are available."
            )
        )

        last_response = None

        for attempt in range(
            2
        ):
            if attempt == 0:
                search_prompt = (
                    base_prompt
                )

            else:
                search_prompt = (
                    base_prompt
                    + "\n\n"
                    + (
                        "IMPORTANT: The previous attempt "
                        "did not return usable Google "
                        "Search grounding metadata. "
                        "Perform Google Search and base "
                        "the response on the retrieved "
                        "web sources."
                    )
                )

            payload = {
                "contents": [
                    {
                        "role":
                        "user",

                        "parts": [
                            {
                                "text":
                                search_prompt
                            }
                        ],
                    }
                ],

                "tools": [
                    {
                        "google_search": {}
                    }
                ],

                "generationConfig": {
                    "maxOutputTokens":
                    5000,

                    # Research and fact checking benefit
                    # from some reasoning, but we keep
                    # it restrained for cost/latency.
                    "thinkingConfig": {
                        "thinkingLevel":
                        "low"
                    },

                    "temperature":
                    0.1,
                },
            }

            response = self.call(
                payload,
                model,
            )

            last_response = (
                response
            )

            sources = self.sources(
                response
            )

            if sources:
                return {
                    "text":
                    self.output(
                        response
                    ),

                    "sources":
                    sources,
                }

        raise ProductionError(
            "Gemini research completed without "
            "usable Google Search sources. "
            "Response: "
            + str(
                last_response
            )[:1000]
        )