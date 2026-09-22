import datetime
import sqlite3
from .utils import ProductionError


class BudgetError(ProductionError):
    pass


class Budget:
    """Conservative reservation ledger. Not a provider invoice or account-wide hard cap."""

    def __init__(self, settings, run_id):
        self.settings, self.run_id = settings, run_id
        self.db = sqlite3.connect(str(settings.root / ".cache/costs.sqlite"))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS costs (month TEXT, run TEXT, service TEXT, usd REAL)"
        )

    def reserve(self, service, usd):
        month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            total = self.db.execute(
                "SELECT COALESCE(SUM(usd),0) FROM costs WHERE month=?", (month,)
            ).fetchone()[0]
            run = self.db.execute(
                "SELECT COALESCE(SUM(usd),0) FROM costs WHERE run=?", (self.run_id,)
            ).fetchone()[0]
            v = self.settings.video
            if total + usd > v["monthly_budget_usd"] or run + usd > v["run_budget_usd"]:
                raise BudgetError(
                    "Local estimated spend limit reached. See config/video.json and .cache/costs.sqlite."
                )
            self.db.execute(
                "INSERT INTO costs VALUES (?,?,?,?)", (month, self.run_id, service, usd)
            )

    def summary(self):
        return dict(
            self.db.execute(
                "SELECT service,SUM(usd) FROM costs WHERE run=? GROUP BY service",
                (self.run_id,),
            )
        )
