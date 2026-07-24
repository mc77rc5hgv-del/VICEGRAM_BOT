from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    months: int
    price_rub: int
    price_stars: int
    emoji: str

    @property
    def price_per_month(self) -> float:
        return self.price_rub / self.months

    @property
    def discount_percent(self) -> int:
        base = PLANS_BY_KEY["1m"].price_rub
        if self.months == 1:
            return 0
        return round((1 - (self.price_per_month / base)) * 100)


# Same tiers/discount structure as the reference service, priced ~40% lower.
# Longest plan first, matching the reference bot's "best deal up top" layout.
PLANS: list[Plan] = [
    Plan(key="12m", label="12 месяцев", months=12, price_rub=1190, price_stars=1190, emoji="💥"),
    Plan(key="6m", label="6 месяцев", months=6, price_rub=699, price_stars=700, emoji="🚀"),
    Plan(key="3m", label="3 месяца", months=3, price_rub=389, price_stars=390, emoji="🤩"),
    Plan(key="1m", label="1 месяц", months=1, price_rub=149, price_stars=150, emoji="👍"),
]

PLANS_BY_KEY: dict[str, Plan] = {p.key: p for p in PLANS}
