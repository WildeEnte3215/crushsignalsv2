from .schemas import Plan
from .utils import ProductionError


MAX_GENERATION_ATTEMPTS = 3


def validate_plan(plan, evidence):
    """
    Validate factual grounding and structural requirements.

    Returns a list of human-readable issues.
    An empty list means the plan is valid.
    """
    issues = []

    # -----------------------------------------------------
    # UNIQUE SCENE IDS
    # -----------------------------------------------------

    scene_ids = [
        scene.id
        for scene in plan.scenes
    ]

    if len(set(scene_ids)) != len(scene_ids):
        issues.append(
            "Scene IDs must be unique."
        )

    # -----------------------------------------------------
    # HOOK MUST MATCH FIRST SCENE EXACTLY
    # -----------------------------------------------------

    if not plan.scenes:
        issues.append(
            "Plan contains no scenes."
        )

    elif plan.hook.strip() != plan.scenes[0].narration.strip():
        issues.append(
            "Hook must exactly equal the first scene narration."
        )

    # -----------------------------------------------------
    # CLAIM GROUNDING
    # -----------------------------------------------------

    known_claim_ids = {
        claim.id
        for claim in evidence.claims
    }

    for scene in plan.scenes:
        if not scene.claim_ids:
            issues.append(
                "Scene %s has no claim IDs."
                % scene.id
            )
            continue

        unknown = [
            claim_id
            for claim_id in scene.claim_ids
            if claim_id not in known_claim_ids
        ]

        if unknown:
            issues.append(
                "Scene %s uses unsupported claim IDs: %s"
                % (
                    scene.id,
                    ", ".join(unknown),
                )
            )

    # -----------------------------------------------------
    # SCRIPT LENGTH
    # -----------------------------------------------------

    word_count = sum(
        len(
            scene.narration.split()
        )
        for scene in plan.scenes
    )

    if not 55 <= word_count <= 150:
        issues.append(
            "Narration contains %d words; required range is 55-150."
            % word_count
        )

    return issues


def generate(
    ai,
    settings,
    topic,
    evidence,
    feedback="",
):
    """
    Generate a grounded WORLD IN 60 content plan.

    Invalid model outputs are automatically regenerated
    up to MAX_GENERATION_ATTEMPTS times.

    Unsupported claim IDs are NEVER silently remapped.
    """

    content_prompt = settings.prompt(
        "content"
    ).replace(
        "{target_words}",
        str(
            settings.video[
                "target_words"
            ]
        ),
    )

    valid_claim_ids = [
        claim.id
        for claim in evidence.claims
    ]

    if not valid_claim_ids:
        raise ProductionError(
            "Research contains no usable claim IDs."
        )

    claim_contract = """
STRICT CLAIM-ID CONTRACT

The ONLY allowed values inside scene.claim_ids are:

%s

For EVERY scene:

- claim_ids must contain at least one value.
- Copy claim IDs EXACTLY from the allowed list above.
- Never use the scene ID as a claim ID.
- Never invent a claim ID.
- Never use values such as scene_1, scene_2 or scene_3 as claim IDs unless such a value literally appears in the allowed claim-ID list.
- A scene may reference multiple allowed claims when the narration genuinely uses all of them.
- Do not reference a claim merely because it is related to the topic.
- Each referenced claim must actually support the narration in that scene.

STRUCTURAL CONTRACT

- Every scene ID must be unique.
- The hook must EXACTLY equal the narration of the first scene.
- Total scene narration must contain between 55 and 150 words.
- Follow the supplied Plan schema exactly.
- Return only the requested structured Plan.
""" % (
        "\n".join(
            "- " + claim_id
            for claim_id
            in valid_claim_ids
        )
    )

    previous_issues = []

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1,
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
            content_prompt
            + "\n\n"
            + claim_contract
            + "\n\nTOPIC:\n"
            + topic
            + "\n\nRESEARCH:\n"
            + evidence.model_dump_json()
            + "\n\nREVISION FEEDBACK:\n"
            + revision_feedback
            + retry_feedback
        )

        plan = ai.structured(
            prompt,
            Plan,
        )

        issues = validate_plan(
            plan,
            evidence,
        )

        if not issues:
            return plan

        previous_issues = issues

        print(
            "[RETRY] Invalid content plan "
            "(attempt %d/%d): %s"
            % (
                attempt,
                MAX_GENERATION_ATTEMPTS,
                "; ".join(issues),
            ),
            flush=True,
        )

    raise ProductionError(
        "Content plan remained invalid after %d attempts: %s"
        % (
            MAX_GENERATION_ATTEMPTS,
            "; ".join(
                previous_issues
            ),
        )
    )