from .schemas import Topic

FIRST_TOPIC = "Why airplane windows have tiny holes"


def choose(ai, completed):
    if not completed:
        return FIRST_TOPIC
    return ai.structured(
        "Choose one concrete everyday engineering curiosity question for an English Short. "
        "Avoid medical, legal, political or financial advice. Do not repeat any of these topics: "
        + "\n".join(completed),
        Topic,
        model=ai.s.video["vision_model"],
    ).topic
