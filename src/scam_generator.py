from .schemas import ScamShort
from .utils import ProductionError


SCAM_MODEL = "gpt-5.6-luna"
MAX_SCAM_GENERATION_ATTEMPTS = 3


def validate_scam_short(short, evidence):
    """
    Validate the generated scam/safety Short.

    Returns a list of human-readable issues.
    An empty list means the concept is valid.
    """

    issues = []

    # -----------------------------------------------------
    # RESEARCH MUST EXIST
    # -----------------------------------------------------

    if not evidence.claims:
        issues.append(
            "Research contains no usable claims."
        )

    # -----------------------------------------------------
    # CATEGORY LABEL
    # -----------------------------------------------------

    if (
        short.category_label
        .strip()
        .upper()
        != "SCAM WARNING"
    ):
        issues.append(
            'category_label must be exactly "SCAM WARNING".'
        )

    # -----------------------------------------------------
    # HOOK / TITLE QUALITY
    # -----------------------------------------------------

    hook = short.hook.strip()

    if len(hook) < 8:
        issues.append(
            "Hook is too short."
        )

    if len(hook) > 90:
        issues.append(
            "Hook is too long."
        )

    weak_hooks = (
        "did you know",
        "here are some",
        "be careful online",
        "some scam facts",
    )

    if any(
        phrase in hook.lower()
        for phrase in weak_hooks
    ):
        issues.append(
            "Hook is too vague or generic."
        )

    # -----------------------------------------------------
    # POINT COUNT
    # -----------------------------------------------------

    if not 3 <= len(short.points) <= 5:
        issues.append(
            "Short must contain between 3 and 5 points."
        )

    # -----------------------------------------------------
    # POINT QUALITY
    # -----------------------------------------------------

    normalized_points = []

    for index, point in enumerate(
        short.points,
        start=1,
    ):
        cleaned = point.strip()

        if len(cleaned) < 8:
            issues.append(
                "Point %d is too short."
                % index
            )

        if len(cleaned) > 130:
            issues.append(
                "Point %d is too long."
                % index
            )

        normalized = (
            cleaned
            .lower()
            .strip(" .!?")
        )

        if normalized in normalized_points:
            issues.append(
                "Point %d duplicates another point."
                % index
            )

        normalized_points.append(
            normalized
        )

    # -----------------------------------------------------
    # CTA
    # -----------------------------------------------------

    if short.cta:
        if len(short.cta.strip()) > 80:
            issues.append(
                "CTA is too long."
            )

    # -----------------------------------------------------
    # BACKGROUND QUERY
    # -----------------------------------------------------

    query = (
        short.background_search_query
        .strip()
    )

    if len(query.split()) < 2:
        issues.append(
            "Background search query is too vague."
        )

    if len(query.split()) > 10:
        issues.append(
            "Background search query is too long."
        )

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    if not (
        8
        <= short.estimated_duration_seconds
        <= 16
    ):
        issues.append(
            "Estimated duration must be between 8 and 16 seconds."
        )

    return issues


def generate_scam_short(
    ai,
    settings,
    topic,
    evidence,
    feedback="",
):
    """
    Generate one grounded SCAM / DIGITAL SAFETY text Short.

    GPT-5.6 Luna is used explicitly.
    Gemini is never used by this generator.
    """

    scam_prompt = settings.prompt(
        "scam"
    )

    claim_lines = []

    for claim in evidence.claims:
        claim_lines.append(
            "%s: %s"
            % (
                claim.id,
                claim.statement,
            )
        )

    if not claim_lines:
        raise ProductionError(
            "Research contains no usable claims."
        )

    grounding_contract = """
STRICT FACTUAL GROUNDING CONTRACT

You are creating ONE short-form safety video.

Use ONLY information supported by the supplied research.

SUPPORTED RESEARCH CLAIMS:

%s

RULES:

- Every factual point in the Short must be supported by the research.
- Do not invent statistics.
- Do not invent bank policies.
- Do not invent laws.
- Do not invent platform rules.
- Do not exaggerate a warning sign into proof of fraud.
- Preserve uncertainty when the research is uncertain.
- Prefer practical defensive advice.
- Never tell the viewer to interact with a suspicious link, sender, QR code, payment request, or account in order to test it.
- Keep the wording concise enough for a text-only vertical Short.
- category_label must be exactly: SCAM WARNING
- Use 3 to 5 points.
- estimated_duration_seconds must be between 8 and 16.
- background_search_query should describe ONE simple stock-video background.
- Do not request multiple clips.
- Return only the requested ScamShort structure.
""" % (
        "\n".join(
            "- " + line
            for line in claim_lines
        )
    )

    previous_issues = []

    for attempt in range(
        1,
        MAX_SCAM_GENERATION_ATTEMPTS + 1,
    ):
        retry_feedback = ""

        if previous_issues:
            retry_feedback = (
                "\n\nYOUR PREVIOUS OUTPUT WAS INVALID.\n"
                "Fix ALL of these problems:\n"
                + "\n".join(
                    "- " + issue
                    for issue
                    in previous_issues
                )
                + "\nDo not repeat these errors."
            )

        revision_feedback = (
            feedback.strip()
            if feedback
            else "None."
        )

        prompt = (
            scam_prompt
            + "\n\n"
            + grounding_contract
            + "\n\nTOPIC:\n"
            + topic
            + "\n\nFULL RESEARCH:\n"
            + evidence.model_dump_json()
            + "\n\nREVISION FEEDBACK:\n"
            + revision_feedback
            + retry_feedback
        )

        short = ai.structured(
            prompt,
            ScamShort,
            model=SCAM_MODEL,
        )

        issues = validate_scam_short(
            short,
            evidence,
        )

        if not issues:
            return short

        previous_issues = issues

        print(
            "[RETRY] Invalid scam Short "
            "(attempt %d/%d): %s"
            % (
                attempt,
                MAX_SCAM_GENERATION_ATTEMPTS,
                "; ".join(issues),
            ),
            flush=True,
        )

    raise ProductionError(
        "Scam Short remained invalid after %d attempts: %s"
        % (
            MAX_SCAM_GENERATION_ATTEMPTS,
            "; ".join(
                previous_issues
            ),
        )
    )