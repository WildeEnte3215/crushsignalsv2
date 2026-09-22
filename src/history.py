import datetime
import re

from .utils import read, save


class History:
    def __init__(self, root):
        self.root = root
        self.path = root / "history.json"
        self.data = read(
            self.path,
            {
                "runs": [],
            },
        )

    def unfinished(
        self,
        mode=None,
    ):
        """
        Return the newest unfinished run.

        If mode is supplied, only return an unfinished
        run belonging to that production mode.

        Legacy runs without a mode are treated as normal.
        """

        for run in reversed(
            self.data["runs"]
        ):
            if (
                run.get(
                    "status"
                )
                == "complete"
            ):
                continue

            run_mode = run.get(
                "mode",
                "normal",
            )

            if (
                mode is None
                or run_mode == mode
            ):
                return run

        return None

    def new(
        self,
        topic,
        mode="normal",
    ):
        now = datetime.datetime.now(
            datetime.timezone.utc
        )

        slug = re.sub(
            "[^a-z0-9]+",
            "_",
            topic.lower(),
        ).strip(
            "_"
        )[:65]

        run = {
            "id": (
                now.strftime(
                    "%Y%m%d_%H%M%S_%f"
                )
                + "_"
                + slug
            ),
            "topic": topic,
            "mode": mode,
            "created": now.isoformat(),
            "status": "running",
        }

        self.data[
            "runs"
        ].append(
            run
        )

        save(
            self.path,
            self.data,
        )

        return run

    def update(
        self,
        run,
        **fields,
    ):
        run.update(
            fields
        )

        save(
            self.path,
            self.data,
        )