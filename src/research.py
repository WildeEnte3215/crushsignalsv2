import json

from urllib.parse import urlparse

from .schemas import Research, Verdict
from .tavily_client import Tavily
from .utils import ProductionError


MAX_RESEARCH_ATTEMPTS = 3
MAX_FACT_CHECK_ATTEMPTS = 3


def _tavily(
    ai,
    settings=None,
):
    settings = (
        settings
        or getattr(
            ai,
            "s",
            None,
        )
    )

    http = getattr(
        ai,
        "http",
        None,
    )

    cache = getattr(
        ai,
        "cache",
        None,
    )

    if (
        settings is None
        or http is None
        or cache is None
    ):
        raise ProductionError(
            "AI client does not expose the settings, "
            "HTTP client and cache required by Tavily."
        )

    return Tavily(
        settings,
        http,
        cache,
    )


def _hostname(url):
    try:
        host = (
            urlparse(
                url
            ).hostname
            or ""
        ).lower()
    except ValueError:
        return ""

    if host.startswith(
        "www."
    ):
        host = host[4:]

    return host


def _allowed_sources(
    bundle,
):
    sources = bundle.get(
        "sources",
        {},
    )

    if not isinstance(
        sources,
        dict,
    ):
        raise ProductionError(
            "Tavily source map is invalid."
        )

    allowed = {
        str(url).strip()
        for url in sources
        if str(url).strip()
    }

    if len(allowed) < 2:
        raise ProductionError(
            "Tavily returned fewer than two usable sources."
        )

    hosts = {
        _hostname(
            url
        )
        for url in allowed
        if _hostname(
            url
        )
    }

    if len(hosts) < 2:
        raise ProductionError(
            "Tavily returned fewer than two "
            "independent source domains."
        )

    return allowed


def _research_material(
    bundle,
):
    return {
        "query":
        bundle.get(
            "query",
            "",
        ),

        "sources":
        bundle.get(
            "sources",
            {},
        ),

        "results":
        bundle.get(
            "results",
            [],
        ),
    }


def research(
    ai,
    settings,
    topic,
    date,
):
    """
    Search the web with Tavily, then use the selected
    AI provider only to convert the retrieved evidence
    into grounded structured research.

    Tavily performs the actual web search.
    Gemini/OpenAI never gets permission to invent or
    independently browse for additional sources here.
    """

    tavily = _tavily(
        ai,
        settings,
    )

    query = (
        str(topic).strip()
        + " explanation mechanism technical facts "
        + "official primary authoritative sources"
    )

    evidence = tavily.bundle(
        query=query,
        depth="advanced",
        max_results=8,
        topic="general",
    )

    allowed = _allowed_sources(
        evidence
    )

    material = _research_material(
        evidence
    )

    last_error = None

    for attempt in range(
        1,
        MAX_RESEARCH_ATTEMPTS + 1,
    ):
        correction = ""

        if last_error:
            correction = (
                "\n\nPREVIOUS STRUCTURAL PROBLEMS:\n"
                + last_error
                + "\nCorrect every problem above. "
                + "Do not add new facts or URLs."
            )

        result = ai.structured(
            (
                settings.prompt(
                    "research"
                )
                + "\n\nQUESTION:\n"
                + str(topic)
                + "\n\nRESEARCH DATE:\n"
                + str(date)
                + "\n\nIMPORTANT CONTEXT:\n"
                + (
                    "The web search has already been performed "
                    "by Tavily. Use ONLY the evidence supplied "
                    "below. Do not browse independently and do "
                    "not invent missing facts.\n"
                )
                + (
                    "The later script will depend on exact claim "
                    "IDs, so gather enough supported evidence for "
                    "a complete thirty-to-fifty-second explanation."
                )
                + "\n\nSTRUCTURED OUTPUT RULES:\n"
                + (
                    "- Use ONLY URLs present in the supplied "
                    "Tavily source map.\n"
                )
                + "- Never invent URLs.\n"
                + "- Never invent facts.\n"
                + (
                    "- Every claim must have at least one "
                    "supporting source URL.\n"
                )
                + (
                    "- Use simple stable claim IDs such as "
                    "claim_1, claim_2, claim_3.\n"
                )
                + "- Claim IDs must be unique.\n"
                + (
                    "- Each claim should contain one main "
                    "factual idea.\n"
                )
                + "- Include uncertainties where appropriate.\n"
                + (
                    "- Select sources from at least two independent "
                    "domains.\n"
                )
                + (
                    "- Mark primary=true only for a genuine "
                    "primary, official, first-party, academic, "
                    "standards-body, manufacturer, government or "
                    "directly authoritative source.\n"
                )
                + (
                    "- At least one selected source must be marked "
                    "primary when the supplied evidence contains a "
                    "suitable primary or directly authoritative source."
                )
                + correction
                + "\n\nTAVILY WEB EVIDENCE:\n"
                + json.dumps(
                    material,
                    ensure_ascii=False,
                )
            ),
            Research,
        )

        problems = []

        # -------------------------------------------------
        # SOURCE URL GROUNDING
        # -------------------------------------------------

        ungrounded_sources = [
            source.url
            for source
            in result.sources
            if source.url
            not in allowed
        ]

        if ungrounded_sources:
            problems.append(
                "Research contains ungrounded source URLs."
            )

        selected_urls = {
            source.url
            for source
            in result.sources
        }

        # -------------------------------------------------
        # INDEPENDENT DOMAINS
        # -------------------------------------------------

        hosts = {
            _hostname(
                source.url
            )
            for source
            in result.sources
            if _hostname(
                source.url
            )
        }

        if len(hosts) < 2:
            problems.append(
                "Research needs at least two independent "
                "source domains."
            )

        # -------------------------------------------------
        # PRIMARY SOURCE
        # -------------------------------------------------

        if not any(
            source.primary
            for source
            in result.sources
        ):
            print(
                (
                    "[WARN] No primary or directly authoritative "
                    "source selected. Continuing because the "
                    "research is still grounded in multiple "
                    "independent sources."
                ),
                flush=True,
            )

        # -------------------------------------------------
        # CLAIM IDS
        # -------------------------------------------------

        claim_ids = [
            claim.id
            for claim
            in result.claims
        ]

        if (
            len(
                set(
                    claim_ids
                )
            )
            != len(
                claim_ids
            )
        ):
            problems.append(
                "Research claim IDs must be unique."
            )

        # -------------------------------------------------
        # CLAIM SOURCE GROUNDING
        # -------------------------------------------------

        for claim in result.claims:
            if not claim.source_urls:
                problems.append(
                    "Claim %s has no source URL."
                    % claim.id
                )

                continue

            claim_urls = set(
                claim.source_urls
            )

            if not claim_urls <= allowed:
                problems.append(
                    "Claim %s references a source URL "
                    "that was not returned by Tavily."
                    % claim.id
                )

            if not claim_urls <= selected_urls:
                problems.append(
                    "Claim %s references a URL that is "
                    "not listed in Research.sources."
                    % claim.id
                )

        if not problems:
            return result

        last_error = "; ".join(
            problems
        )

        print(
            (
                "[RETRY] Invalid research grounding "
                "(attempt %d/%d): %s"
            )
            % (
                attempt,
                MAX_RESEARCH_ATTEMPTS,
                last_error,
            ),
            flush=True,
        )

    raise ProductionError(
        (
            "Research remained invalid after "
            "%d attempts: %s"
        )
        % (
            MAX_RESEARCH_ATTEMPTS,
            last_error,
        )
    )


def _fact_query(
    plan,
):
    """
    Keep the Tavily query compact while still changing
    when the actual script changes.

    This means a rewritten script can trigger a genuinely
    fresh fact-check search instead of silently reusing the
    first search forever.
    """

    parts = [
        str(
            plan.topic
        ).strip(),
        "fact check technical explanation",
    ]

    for scene in plan.scenes:
        text = " ".join(
            str(
                scene.narration
            ).split()
        )

        if text:
            parts.append(
                text[:52]
            )

    query = " ".join(
        parts
    )

    return query[:390].rstrip()


def fact_check(
    ai,
    plan,
):
    """
    Independently verify every narrated scene.

    A fresh Tavily web search supplies the evidence.
    The AI provider only evaluates the supplied search
    evidence and returns the strict Verdict structure.

    Genuine factual problems are returned normally so
    the pipeline can revise the script. Structural
    failures are retried without spending another
    Tavily credit because the search response is cached.
    """

    tavily = _tavily(
        ai
    )

    expected_scene_ids = [
        scene.id
        for scene
        in plan.scenes
    ]

    expected_scene_set = set(
        expected_scene_ids
    )

    scene_contract = "\n".join(
        "- " + scene_id
        for scene_id
        in expected_scene_ids
    )

    query = _fact_query(
        plan
    )

    checked = tavily.bundle(
        query=query,
        depth="basic",
        max_results=8,
        topic="general",
    )

    allowed_sources = _allowed_sources(
        checked
    )

    audit_material = _research_material(
        checked
    )

    last_error = None

    for attempt in range(
        1,
        MAX_FACT_CHECK_ATTEMPTS + 1,
    ):
        correction = ""

        if last_error:
            correction = (
                "\n\nPREVIOUS STRUCTURAL PROBLEMS:\n"
                + last_error
                + "\nCorrect every structural problem above "
                + "without inventing facts, URLs or scene IDs."
            )

        verdict = ai.structured(
            (
                "Independently fact-check EVERY narrated factual "
                "claim in this WORLD IN 60 script using ONLY the "
                "fresh Tavily web evidence supplied below.\n\n"
                "Do NOT presume the script is correct.\n"
                "Look specifically for:\n"
                "- factual errors\n"
                "- unsupported causal explanations\n"
                "- misleading simplifications\n"
                "- unsupported numbers\n"
                "- claims that are only partly true\n"
                "- claims that vary by design or implementation\n\n"
                "SCENE COVERAGE CONTRACT\n"
                "You MUST explicitly evaluate EVERY one of these "
                "scene IDs:\n"
                + scene_contract
                + "\n\n"
                + (
                    "Do not skip a scene merely because it appears "
                    "similar to another scene.\n"
                )
                + (
                    "For every scene, determine whether its narration "
                    "is supported by the supplied reliable evidence.\n"
                )
                + (
                    "Do not use model memory as evidence when the "
                    "supplied web evidence does not support a claim.\n"
                )
                + (
                    "If the evidence is insufficient for a material "
                    "claim, treat that as a factual issue rather than "
                    "guessing.\n\n"
                )
                + (
                    "If a scene contains no material factual problem, "
                    "record that it was checked and supported.\n"
                )
                + (
                    "If a scene contains a problem, identify the exact "
                    "problem in issues.\n\n"
                )
                + "STRICT VERDICT RULES:\n"
                + (
                    "- checked_scene_ids MUST contain EVERY expected "
                    "scene ID exactly once.\n"
                )
                + "- Do not invent scene IDs.\n"
                + (
                    "- passed may be true ONLY if every scene is "
                    "materially supported.\n"
                )
                + (
                    "- If any scene has a material factual problem, "
                    "passed must be false.\n"
                )
                + "- Put concrete factual problems in issues.\n"
                + (
                    "- If there are no material issues, issues must "
                    "be empty.\n"
                )
                + (
                    "- evidence_urls must contain ONLY URLs from the "
                    "supplied Tavily source map.\n"
                )
                + (
                    "- Use at least two independent grounded evidence "
                    "URLs when available.\n"
                )
                + "- Never invent a URL.\n"
                + correction
                + "\n\nSCRIPT PLAN:\n"
                + plan.model_dump_json()
                + "\n\nFRESH TAVILY FACT-CHECK EVIDENCE:\n"
                + json.dumps(
                    audit_material,
                    ensure_ascii=False,
                )
            ),
            Verdict,
        )

        problems = []

        # -------------------------------------------------
        # SCENE COVERAGE
        # -------------------------------------------------

        returned_scene_set = set(
            verdict.checked_scene_ids
        )

        missing = (
            expected_scene_set
            - returned_scene_set
        )

        extra = (
            returned_scene_set
            - expected_scene_set
        )

        if missing:
            problems.append(
                "Missing scene IDs: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        if extra:
            problems.append(
                "Unexpected scene IDs: "
                + ", ".join(
                    sorted(
                        extra
                    )
                )
            )

        if (
            len(
                verdict.checked_scene_ids
            )
            != len(
                expected_scene_ids
            )
            or len(
                returned_scene_set
            )
            != len(
                verdict.checked_scene_ids
            )
        ):
            problems.append(
                "Fact checker returned duplicate or "
                "incomplete scene coverage."
            )

        # -------------------------------------------------
        # GROUNDED EVIDENCE
        # -------------------------------------------------

        evidence_urls = [
            url
            for url
            in verdict.evidence_urls
            if url
        ]

        if len(
            set(
                evidence_urls
            )
        ) < 2:
            problems.append(
                "Fact check returned fewer than two "
                "independent evidence URLs."
            )

        invalid_urls = [
            url
            for url
            in evidence_urls
            if url
            not in allowed_sources
        ]

        if invalid_urls:
            problems.append(
                "Fact check returned evidence URLs "
                "not present in the Tavily source map."
            )

        evidence_hosts = {
            _hostname(
                url
            )
            for url
            in evidence_urls
            if _hostname(
                url
            )
        }

        if len(evidence_hosts) < 2:
            problems.append(
                "Fact check evidence must cover at least "
                "two independent source domains."
            )

        # -------------------------------------------------
        # VERDICT CONSISTENCY
        # -------------------------------------------------

        if (
            verdict.passed
            and verdict.issues
        ):
            problems.append(
                "Fact checker marked passed=true while "
                "also returning factual issues."
            )

        if (
            not verdict.passed
            and not verdict.issues
        ):
            problems.append(
                "Fact checker marked passed=false without "
                "describing any factual issue."
            )

        # -------------------------------------------------
        # STRUCTURALLY VALID
        # -------------------------------------------------

        if not problems:
            return verdict

        last_error = "; ".join(
            problems
        )

        print(
            (
                "[RETRY] Incomplete fact check "
                "(attempt %d/%d): %s"
            )
            % (
                attempt,
                MAX_FACT_CHECK_ATTEMPTS,
                last_error,
            ),
            flush=True,
        )

    raise ProductionError(
        (
            "Fact checker remained structurally incomplete "
            "after %d attempts: %s"
        )
        % (
            MAX_FACT_CHECK_ATTEMPTS,
            last_error,
        )
    )
