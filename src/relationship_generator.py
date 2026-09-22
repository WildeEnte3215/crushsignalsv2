from .schemas import RelationshipShort
from .utils import ProductionError


RELATIONSHIP_MODEL = "gpt-5.6-luna"
MAX_RELATIONSHIP_GENERATION_ATTEMPTS = 3


def validate_relationship_short(short):
    """
    Validate one Relationship / Crush text Short.

    Returns a list of human-readable issues.
    An empty list means the concept is valid.
    """

    issues = []

    # -----------------------------------------------------
    # HOOK
    # -----------------------------------------------------

    hook = short.hook.strip()

    weak_hooks = (
        "did you know",
        "relationship facts",
        "interesting love facts",
        "some psychology facts",
        "psychology says",
        "studies show",
    )

    if any(
        phrase in hook.lower()
        for phrase in weak_hooks
    ):
        issues.append(
            "Hook is too vague or sounds like fake psychology."
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

    banned_phrases = (
        "psychology says",
        "studies show",
        "science proves",
        "this means they definitely",
        "this proves they",
        "they are definitely",
        "they 100%",
        "always means",
    )

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

        if len(cleaned) > 115:
            issues.append(
                "Point %d is too long."
                % index
            )

        lowered = cleaned.lower()

        if any(
            phrase in lowered
            for phrase in banned_phrases
        ):
            issues.append(
                "Point %d makes an overly certain or fake scientific claim."
                % index
            )

        normalized = (
            lowered
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
    # BACKGROUND QUERY
    # -----------------------------------------------------

    query = (
        short.background_search_query
        .strip()
    )

    word_count = len(
        query.split()
    )

    if word_count < 2:
        issues.append(
            "Background search query is too vague."
        )

    if word_count > 9:
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


def generate_relationship_short(
    ai,
    settings,
    topic,
    feedback="",
):
    """
    Generate one Relationship / Crush text Short.

    No web research is used by default.

    The content is intentionally framed as relatable
    social signals rather than scientific certainty.
    """

    content_prompt = settings.prompt(
        "relationship"
    )

    generation_contract = """
STRICT CONTENT CONTRACT

Create ONE short-form relationship / crush video.

This is relatable social content, NOT medical,
scientific, or psychological diagnosis.

RULES:

- Do not claim that a behavior proves attraction.
- Do not write "psychology says".
- Do not invent studies or statistics.
- Do not use fake scientific authority.
- Do not claim to know exactly what another person thinks.
- Avoid words like "always", "definitely", or "guaranteed"
  when describing attraction.
- Keep every point specific and relatable.
- Avoid manipulative dating tactics.
- Avoid coercive advice.
- Avoid controlling or obsessive behavior.
- The strongest or most relatable point should usually be last.
- Use 3 to 5 points.
- Keep each point short.
- Use ONE aesthetic stock-video background.
- background_search_query must contain 2 to 9 simple words.
- estimated_duration_seconds must be between 8 and 16.
- CTA must always be returned as a string.
- If no CTA is useful, return an empty string.
- Return only the requested RelationshipShort structure.
"""

    previous_issues = []

    for attempt in range(
        1,
        MAX_RELATIONSHIP_GENERATION_ATTEMPTS + 1,
    ):
        retry_feedback = ""

        if previous_issues:
            retry_feedback = (
                "\n\nYOUR PREVIOUS OUTPUT WAS INVALID.\n"
                "Fix ALL of these problems:\n"
                + "\n".join(
                    "- " + issue
                    for issue in previous_issues
                )
                + "\nDo not repeat these errors."
            )

        revision_feedback = (
            feedback.strip()
            if feedback
            else "None."
        )

        prompt = (
            content_prompt
            + "\n\n"
            + generation_contract
            + "\n\nTOPIC:\n"
            + topic
            + "\n\nREVISION FEEDBACK:\n"
            + revision_feedback
            + retry_feedback
        )

        short = ai.structured(
            prompt,
            RelationshipShort,
            model=RELATIONSHIP_MODEL,
        )

        issues = validate_relationship_short(
            short
        )

        if not issues:
            return short

        previous_issues = issues

        print(
            "[RETRY] Invalid relationship Short "
            "(attempt %d/%d): %s"
            % (
                attempt,
                MAX_RELATIONSHIP_GENERATION_ATTEMPTS,
                "; ".join(
                    issues
                ),
            ),
            flush=True,
        )

    raise ProductionError(
        "Relationship Short remained invalid after %d attempts: %s"
        % (
            MAX_RELATIONSHIP_GENERATION_ATTEMPTS,
            "; ".join(
                previous_issues
            ),
        )
    )