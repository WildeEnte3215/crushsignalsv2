import json
from urllib.parse import urlparse

from .schemas import Research
from .tavily_client import Tavily
from .utils import ProductionError


SCAM_MODEL = "gpt-5.6-luna"
MAX_SCAM_RESEARCH_ATTEMPTS = 2


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
            "Tavily returned fewer than two independent source domains."
        )

    return allowed


def research_scam(
    ai,
    settings,
    topic,
    date,
):
    """
    Research one Scam / Digital Safety Short.

    Tavily performs the web search.
    GPT-5.6 Luna only structures the supplied evidence.

    No Gemini calls are used.
    """

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
        http is None
        or cache is None
    ):
        raise ProductionError(
            "OpenAI client does not expose HTTP/cache for Tavily."
        )

    tavily = Tavily(
        settings,
        http,
        cache,
    )

    query = (
        str(topic).strip()
        + " scam fraud phishing digital safety "
        + "official consumer protection cybersecurity "
        + "bank security authoritative advice"
    )

    print(
        "[STEP] Tavily scam research",
        flush=True,
    )

    evidence = tavily.bundle(
        query=query,
        depth="advanced",
        max_results=6,
        topic="general",
    )

    allowed = _allowed_sources(
        evidence
    )

    material = {
        "query": evidence.get(
            "query",
            "",
        ),
        "sources": evidence.get(
            "sources",
            {},
        ),
        "results": evidence.get(
            "results",
            [],
        ),
    }

    last_error = None

    for attempt in range(
        1,
        MAX_SCAM_RESEARCH_ATTEMPTS + 1,
    ):
        correction = ""

        if last_error:
            correction = (
                "\n\nPREVIOUS OUTPUT PROBLEMS:\n"
                + last_error
                + "\nFix every problem without adding "
                + "new facts or URLs."
            )

        prompt = (
            "Create grounded structured research for ONE "
            "very short Scam / Digital Safety YouTube Short.\n\n"

            "The actual web search has already been performed "
            "by Tavily.\n"

            "Use ONLY the supplied Tavily evidence.\n"
            "Do not browse independently.\n"
            "Do not use model memory as evidence.\n"
            "Do not invent facts, URLs, statistics, laws, "
            "bank rules, security policies, or platform rules.\n\n"

            "TOPIC:\n"
            + str(topic)
            + "\n\n"

            "RESEARCH DATE:\n"
            + str(date)
            + "\n\n"

            "STRICT OUTPUT RULES:\n"

            "- Return 2 to 6 strong factual claims.\n"
            "- Claims must be directly useful for the Short.\n"
            "- Every claim must contain at least one source URL.\n"
            "- Every source URL must come EXACTLY from the supplied "
            "Tavily source map.\n"
            "- Every URL used by a claim MUST ALSO appear in "
            "Research.sources.\n"
            "- Never reference a URL in a claim without including "
            "that URL in Research.sources.\n"
            "- Use at least two independent source domains.\n"
            "- Prefer official, government, bank, cybersecurity, "
            "consumer-protection, platform, or other directly "
            "authoritative sources.\n"
            "- Mark primary=true only when the source is genuinely "
            "official or directly authoritative.\n"
            "- Include at least one primary/directly authoritative "
            "source when available.\n"
            "- Use claim IDs claim_1, claim_2, claim_3, etc.\n"
            "- Claim IDs must be unique.\n"
            "- Each claim should contain one main factual idea.\n"
            "- Preserve uncertainty and nuance where necessary.\n"
            "- Do not imply that one warning sign alone proves fraud "
            "unless the evidence genuinely supports that.\n"

            + correction
            + "\n\nTAVILY WEB EVIDENCE:\n"
            + json.dumps(
                material,
                ensure_ascii=False,
            )
        )

        result = ai.structured(
            prompt,
            Research,
            model=SCAM_MODEL,
        )

        problems = []

        selected_urls = {
            source.url
            for source in result.sources
        }

        ungrounded_sources = [
            source.url
            for source in result.sources
            if source.url not in allowed
        ]

        if ungrounded_sources:
            problems.append(
                "Research.sources contains URLs not returned by Tavily."
            )

        hosts = {
            _hostname(
                source.url
            )
            for source in result.sources
            if _hostname(
                source.url
            )
        }

        if len(hosts) < 2:
            problems.append(
                "Research needs at least two independent source domains."
            )

        if not any(
            source.primary
            for source in result.sources
        ):
            problems.append(
                "Research needs at least one primary or directly authoritative source."
            )

        claim_ids = [
            claim.id
            for claim in result.claims
        ]

        if (
            len(
                claim_ids
            )
            != len(
                set(
                    claim_ids
                )
            )
        ):
            problems.append(
                "Research claim IDs must be unique."
            )

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
                    "Claim %s references a URL not returned by Tavily."
                    % claim.id
                )

            if not claim_urls <= selected_urls:
                problems.append(
                    "Claim %s references a URL not listed in Research.sources."
                    % claim.id
                )

        if not problems:
            print(
                "[OK] Scam research grounded",
                flush=True,
            )

            return result

        last_error = "; ".join(
            problems
        )

        print(
            (
                "[RETRY] Invalid scam research "
                "(attempt %d/%d): %s"
            )
            % (
                attempt,
                MAX_SCAM_RESEARCH_ATTEMPTS,
                last_error,
            ),
            flush=True,
        )

    raise ProductionError(
        (
            "Scam research remained invalid after "
            "%d attempts: %s"
        )
        % (
            MAX_SCAM_RESEARCH_ATTEMPTS,
            last_error,
        )
    )