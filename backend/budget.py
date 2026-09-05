"""
Compare a planned trip's estimated cost against the user's stated budget.
Pure calculation — no external APIs — flags overage but never
auto-decides what to cut; that's always the user's call.
"""
from typing import Optional


def calculate_estimated_cost(
    fuel_cost: float = 0,
    food_cost: float = 0,
    stay_cost: float = 0,
    transport_fare: float = 0,
    activity_cost: float = 0,
) -> dict:
    """
    Sum up every cost category we've calculated so far into one estimate,
    keeping the breakdown so we can show the user WHERE the money goes,
    not just a single opaque number.
    """
    breakdown = {
        "fuel": fuel_cost,
        "food": food_cost,
        "stay": stay_cost,
        "transport": transport_fare,
        "activities": activity_cost,
    }
    total = sum(breakdown.values())
    return {"total": round(total, 2), "breakdown": breakdown}


def check_budget(estimated_cost: float, user_budget: Optional[float]) -> dict:
    """
    Compare estimated cost to the user's stated budget.
    Never auto-trims anything — just reports status so the caller
    (eventually an agent) can ask the user what to do.
    """
    if user_budget is None:
        return {"status": "no_budget_set", "estimated_cost": estimated_cost}

    diff = round(estimated_cost - user_budget, 2)

    if diff <= 0:
        return {
            "status": "within_budget",
            "estimated_cost": estimated_cost,
            "budget": user_budget,
            "margin_remaining": round(-diff, 2),
        }

    return {
        "status": "over_budget",
        "estimated_cost": estimated_cost,
        "budget": user_budget,
        "overage": diff,
        "overage_percent": round((diff / user_budget) * 100, 1),
    }


def suggest_trim_options(breakdown: dict, overage: float) -> list[dict]:
    """
    Given the cost breakdown and how much we're over budget, suggest
    WHICH categories could realistically absorb the cut — largest
    categories first, since trimming a big line item gets you to
    budget faster with fewer individual changes.

    This only SUGGESTS where the money is concentrated — it never
    picks for the user. The actual "remove this hotel" or "downgrade
    this" decision stays with them.
    """
    # Sort categories by size, largest first — these are the ones
    # where a change would have the most impact
    sorted_categories = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)

    suggestions = []
    for category, amount in sorted_categories:
        if amount <= 0:
            continue
        suggestions.append({
            "category": category,
            "current_amount": amount,
            "would_need_to_cut": min(amount, overage),  # can't cut more than the category costs
        })

    return suggestions


def apply_user_adjustment(breakdown: dict, category: str, new_amount: float) -> dict:
    """
    Apply a user-specified change to one cost category and return the
    updated breakdown. This is the ONLY way costs change — always driven
    by an explicit user value, never decided by our code.
    """
    if category not in breakdown:
        raise ValueError(f"Unknown category: {category}. Valid: {list(breakdown.keys())}")

    updated = breakdown.copy()
    updated[category] = new_amount
    return updated


def recheck_after_adjustments(breakdown: dict, user_budget: Optional[float]) -> dict:
    """Recalculate total + budget status after one or more user adjustments."""
    new_total = round(sum(breakdown.values()), 2)
    result = check_budget(new_total, user_budget)
    result["breakdown"] = breakdown
    return result


def budget_decision_prompt(check_result: dict) -> str:
    """
    The question we'd ask the user when over budget — offering both
    paths (accept the overage, or trim) rather than assuming either.
    """
    if check_result["status"] != "over_budget":
        return ""

    overage = check_result["overage"]
    return (
        f"This trip is estimated at ₹{check_result['estimated_cost']}, "
        f"which is ₹{overage} over your ₹{check_result['budget']} budget "
        f"({check_result['overage_percent']}% over). "
        f"Would you like to go ahead anyway, or should we look at trimming some costs?"
    )


if __name__ == "__main__":
    breakdown = {
        "fuel": 3500, "food": 4000, "stay": 8000,
        "transport": 6000, "activities": 2000,
    }
    user_budget = 20000

    result = check_budget(sum(breakdown.values()), user_budget)
    print("Initial check:", result)
    print("\n" + budget_decision_prompt(result))

    print("\n--- User decides to trim: stay -> 3000, food -> 500 ---")
    breakdown = apply_user_adjustment(breakdown, "stay", 3000)
    breakdown = apply_user_adjustment(breakdown, "food", 500)

    result = recheck_after_adjustments(breakdown, user_budget)
    print("\nRechecked:", result)

    if result["status"] == "within_budget":
        print(f"Now within budget, with ₹{result['margin_remaining']} to spare.")
    elif result["status"] == "over_budget":
        print(budget_decision_prompt(result))
        suggestions = suggest_trim_options(result["breakdown"], result["overage"])
        print("Further trim options:")
        for s in suggestions:
            print(f"  {s['category']}: ₹{s['current_amount']}")