import base64

from pydantic import ValidationError

from .utils import ProductionError


BASE = "https://api.openai.com/v1"


class OpenAI:
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
            "Authorization":
            "Bearer "
            + settings.keys[
                "OPENAI_API_KEY"
            ]
        }

    @staticmethod
    def output(response):
        if (
            response.get(
                "status"
            )
            != "completed"
        ):
            raise ProductionError(
                "OpenAI response not completed: "
                + str(
                    response.get(
                        "incomplete_details",
                        response.get(
                            "status"
                        ),
                    )
                )
            )

        texts = []

        for item in response.get(
            "output",
            [],
        ):
            for content in item.get(
                "content",
                [],
            ):
                if (
                    content.get(
                        "type"
                    )
                    == "refusal"
                ):
                    raise ProductionError(
                        "OpenAI refused the request."
                    )

                if (
                    content.get(
                        "type"
                    )
                    == "output_text"
                ):
                    texts.append(
                        content[
                            "text"
                        ]
                    )

        if not texts:
            raise ProductionError(
                "OpenAI response contains no output text."
            )

        return "\n".join(
            texts
        )

    @staticmethod
    def sources(response):
        found = {}

        for item in response.get(
            "output",
            [],
        ):
            for src in item.get(
                "action",
                {},
            ).get(
                "sources",
                [],
            ):
                if src.get(
                    "url"
                ):
                    found[
                        src["url"]
                    ] = src.get(
                        "title",
                        src["url"],
                    )

            for content in item.get(
                "content",
                [],
            ):
                for annotation in content.get(
                    "annotations",
                    [],
                ):
                    if (
                        annotation.get(
                            "type"
                        )
                        == "url_citation"
                    ):
                        found[
                            annotation[
                                "url"
                            ]
                        ] = annotation.get(
                            "title",
                            annotation[
                                "url"
                            ],
                        )

        return found

    def call(self, payload):
        hit = self.cache.get(
            "openai",
            payload,
        )

        if hit is not None:
            self.output(
                hit
            )

            return hit

        model = payload[
            "model"
        ]

        rates = self.s.video[
            "rates"
        ][
            model
        ]

        # Conservative token estimate without pretending
        # every character is literally one billed token.
        def input_size(value):
            if isinstance(
                value,
                dict,
            ):
                if (
                    value.get(
                        "type"
                    )
                    == "input_image"
                ):
                    # Local conservative allowance
                    # for a high-detail image.
                    return 4096

                return sum(
                    input_size(v)
                    for v
                    in value.values()
                )

            if isinstance(
                value,
                list,
            ):
                return sum(
                    input_size(v)
                    for v
                    in value
                )

            # Rough text token approximation:
            # about four characters per token.
            return max(
                1,
                len(
                    str(
                        value
                    )
                )
                // 4,
            )

        estimated_input = (
            input_size(
                payload
            )
        )

        # Search carries additional context.
        if payload.get(
            "tools"
        ):
            estimated_input += 8000

        max_output_tokens = int(
            payload.get(
                "max_output_tokens",
                2000,
            )
        )

        cost = (
            estimated_input
            * rates[0]
            + max_output_tokens
            * rates[1]
        ) / 1_000_000

        # Keep a conservative local allowance for
        # web-search tool usage.
        if payload.get(
            "tools"
        ):
            cost += 0.05

        response = self.http.request(
            "POST",
            BASE
            + "/responses",
            self.headers,
            payload,
            before=lambda: self.budget.reserve(
                "OpenAI",
                cost,
            ),
        )

        self.output(
            response
        )

        self.cache.put(
            "openai",
            payload,
            response,
        )

        return response

    def payload(
        self,
        prompt,
        model,
        max_output_tokens=3000,
    ):
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_output_tokens":
            max_output_tokens,
            "store": False,
        }

        if model.startswith(
            "gpt-5"
        ):
            payload[
                "reasoning"
            ] = {
                "effort": "low"
            }

        return payload

    @staticmethod
    def schema_output_limit(
        schema,
    ):
        """
        Use realistic output limits for each
        structured response instead of reserving
        8000 tokens for tiny JSON objects.
        """

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

        content = [
            {
                "type": "input_text",
                "text": prompt,
            }
        ]

        for path in (
            vision
            or []
        ):
            content.append(
                {
                    "type": "input_image",
                    "image_url":
                    (
                        "data:image/jpeg;base64,"
                        + base64.b64encode(
                            path.read_bytes()
                        ).decode()
                    ),
                    "detail": "high",
                }
            )

        payload = self.payload(
            content,
            model,
            max_output_tokens=(
                self.schema_output_limit(
                    schema
                )
            ),
        )

        payload[
            "text"
        ] = {
            "format": {
                "type":
                "json_schema",
                "name":
                schema.__name__,
                "strict":
                True,
                "schema":
                schema.model_json_schema(),
            }
        }

        key = payload.copy()

        hit = self.cache.get(
            "validated",
            key,
        )

        if hit is not None:
            return schema.model_validate(
                hit
            )

        for attempt in range(
            2
        ):
            raw = self.output(
                self.call(
                    payload
                )
            )

            try:
                result = (
                    schema.model_validate_json(
                        raw
                    )
                )

                self.cache.put(
                    "validated",
                    key,
                    result.model_dump(),
                )

                return result

            except (
                ValidationError,
                ValueError,
            ):
                if attempt:
                    raise ProductionError(
                        "OpenAI structured output "
                        "invalid after one repair."
                    ) from None

                payload[
                    "input"
                ] = (
                    payload[
                        "input"
                    ]
                    + [
                        {
                            "role":
                            "assistant",
                            "content":
                            raw,
                        },
                        {
                            "role":
                            "user",
                            "content":
                            (
                                "Repair this JSON to "
                                "exactly satisfy the "
                                "schema. Do not add facts."
                            ),
                        },
                    ]
                )

    def research(
        self,
        prompt,
    ):
        payload = self.payload(
            prompt,
            self.s.video[
                "research_model"
            ],
            max_output_tokens=5000,
        )

        payload.update(
            tools=[
                {
                    "type":
                    "web_search",
                    "search_context_size":
                    "low",
                }
            ],
            tool_choice="required",
            max_tool_calls=5,
            include=[
                "web_search_call.action.sources"
            ],
        )

        response = self.call(
            payload
        )

        if not any(
            item.get(
                "type"
            )
            == "web_search_call"
            for item
            in response.get(
                "output",
                [],
            )
        ):
            raise ProductionError(
                "Research completed without "
                "the required web search."
            )

        sources = self.sources(
            response
        )

        if not sources:
            raise ProductionError(
                "Web research has no source URLs."
            )

        return {
            "text":
            self.output(
                response
            ),
            "sources":
            sources,
        }