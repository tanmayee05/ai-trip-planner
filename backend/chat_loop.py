from trip_slots import TripSlots, next_question
from slot_extraction import update_slots
from geocoding import geocode
from own_vehicle import plan_own_vehicle_route
from connectivity import check_all_modes
from budget import calculate_estimated_cost, check_budget, budget_decision_prompt


def handle_own_vehicle(slots: TripSlots):
    print("\nPlanning your own-vehicle route...")

    source_geo = geocode(slots.source)
    dest_geo = geocode(slots.destination)
    if not source_geo or not dest_geo:
        print("Sorry, I couldn't locate one of those places. Please check the spelling.")
        return

    plan = plan_own_vehicle_route(
        source_geo["lat"], source_geo["lon"],
        dest_geo["lat"], dest_geo["lon"],
        start_time=slots.start_time or "06:00",  # fallback if user skipped it
        preferred_fuel_brand=slots.fuel_brand_preference,
    )

    if not plan:
        print("Couldn't compute the route right now (routing service may be unavailable). Try again shortly.")
        return

    print(f"\nRoute: {plan['distance_km']} km, approx {plan['duration_hr']} hr driving")

    print("\nFuel stops:")
    for stop in plan["fuel_stops"]:
        print(f"  ~{stop['approx_distance_km']}km in, near {stop['area_name']}:")
        if not stop["preferred_brand_found"]:
            print(f"    (Your preferred brand wasn't found here — showing nearest available instead)")
        if not stop["stations"]:
            print("    No named fuel stations found nearby — check locally when you arrive.")
        for s in stop["stations"]:
            brand_label = f" ({s['brand']})" if s["brand"] else ""
            print(f"    {s['name']}{brand_label} — {s['distance_km']}km off route")

    print("\nMeal stops:")
    for stop in plan["meal_stops"]:
        print(f"  {stop['meal']} around {stop['estimated_time']} (~{stop['approx_distance_km']}km in)")

    # Rough fuel cost estimate: ~₹8/km is a reasonable average for a car,
    # this is a placeholder estimate, not a precise calculation
    fuel_cost_estimate = round(plan["distance_km"] * 8)
    check_trip_budget(slots, fuel_cost=fuel_cost_estimate)


def handle_public_transport(slots: TripSlots):
    print("\nChecking transport options...")

    source_geo = geocode(slots.source)
    dest_geo = geocode(slots.destination)
    if not source_geo or not dest_geo:
        print("Sorry, I couldn't locate one of those places. Please check the spelling.")
        return

    travel_date = slots.start_date or "2026-09-15"  # fallback if not given
    result = check_all_modes(
        source_geo["lat"], source_geo["lon"],
        dest_geo["lat"], dest_geo["lon"],
        travel_date=travel_date,
    )

    for mode, data in result.items():
        print(f"\n=== {mode.upper()} ===")
        if data["recommended"]:
            print(f"Recommended: {data['recommended']['name']}")
        else:
            print("No confirmed option found.")
        if "note" in data:
            print(f"Note: {data['note']}")

    check_trip_budget(slots, fuel_cost=0)  # no fuel cost for public transport


def check_trip_budget(slots: TripSlots, fuel_cost: float):
    # Placeholder estimates for pieces we haven't built a real calculator
    # for yet (food/stay/activities) — flagged clearly, not hidden
    cost = calculate_estimated_cost(
        fuel_cost=fuel_cost,
        food_cost=slots.num_days * 500 if slots.num_days else 0,
        stay_cost=slots.num_days * 1500 if slots.num_days else 0,
    )
    print(f"\nEstimated cost: ₹{cost['total']} (breakdown: {cost['breakdown']})")

    result = check_budget(cost["total"], slots.budget)
    if result["status"] == "over_budget":
        print(budget_decision_prompt(result))
    elif result["status"] == "within_budget":
        print(f"Within budget, ₹{result['margin_remaining']} to spare.")
    else:
        print("(No budget was specified, so nothing to compare against.)")


def run():
    slots = TripSlots()
    last_question = None
    print("Bot: Hi! Tell me about the trip you want to plan.")

    while True:
        user_message = input("You: ")
        slots = update_slots(slots, user_message, last_question)

        question = next_question(slots)
        if question is None:
            print("Bot: Great, I have everything I need! Let me put this together...")
            if slots.travel_mode == "own_vehicle":
                handle_own_vehicle(slots)
            else:
                handle_public_transport(slots)
            break
        else:
            print(f"Bot: {question}")
            last_question = question


if __name__ == "__main__":
    run()