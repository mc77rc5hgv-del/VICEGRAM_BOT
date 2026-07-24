from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    months: int
    price_rub: int
    price_stars: int


# Same tiers/discount structure as the reference service, priced ~40% lower.
PLANS: list[Plan] = [
    Plan(key="1m", label="1 месяц", months=1, price_rub=149, price_stars=150),
    Plan(key="3m", label="3 месяца", months=3, price_rub=389, price_stars=390),
    Plan(key="6m", label="6 месяцев", months=6, price_rub=699, price_stars=700),
    Plan(key="12m", label="12 месяцев", months=12, price_rub=1190, price_stars=1190),
]

PLANS_BY_KEY: dict[str, Plan] = {p.key: p for p in PLANS}
