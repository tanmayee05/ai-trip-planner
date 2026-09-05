from typing import Optional, Literal
from pydantic import BaseModel, Field


class TripSlots(BaseModel):
    """The flexible "form" we fill in over the conversation.

    The Field descriptions double as the schema the LLM sees when this model is
    passed to `.with_structured_output(TripSlots)` in slot_extraction.py, so keep
    them short and unambiguous.
    """

    destination: Optional[str] = Field(
        None, description="The place/city the user wants to travel to"
    )
    source: Optional[str] = Field(
        None, description="The place the user is starting their journey from"
    )
    num_days: Optional[int] = Field(
        None, description="Total number of days for the trip"
    )
    start_date: Optional[str] = Field(
        None, description="Trip start date as YYYY-MM-DD, only if explicitly stated"
    )
    end_date: Optional[str] = Field(
        None, description="Trip return/end date as YYYY-MM-DD"
    )
    num_people: Optional[int] = Field(
        None, description="Number of people travelling"
    )
    budget: Optional[float] = Field(
        None, description="Total trip budget as a plain number"
    )
    travel_mode: Optional[Literal["own_vehicle", "public_transport"]] = Field(
        None,
        description="How the user travels: 'own_vehicle' or 'public_transport'",
    )
    # --- new fields below, only meaningful when travel_mode == "own_vehicle" ---
    start_time: Optional[str] = Field(
        None,
        description="What time the user plans to start the journey, formatted as 24-hour HH:MM, e.g. '06:00' for 6am",
    )
    fuel_brand_preferences: Optional[list[str]] = Field(
        None,
        description="One or more preferred fuel station brands if travelling by own vehicle, e.g. ['HP', 'Indian Oil'] — user may give more than one",
    )


# The order we ask questions in — top to bottom
REQUIRED_FIELDS = ["destination", "source", "num_days", "start_date", "end_date", "budget", "travel_mode"]

QUESTIONS = {
    "destination": "Where would you like to go?",
    "source": "Where are you starting your journey from?",
    "num_days": "How many days is the trip?",
    "start_date": "When would you like to start (YYYY-MM-DD)?",
    "end_date": "And what date do you plan to return (YYYY-MM-DD)?",
    "budget": "What's your approximate budget for the trip, in rupees?",
    "travel_mode": "Will you travel by your own vehicle, or public transport?",
}

# NEW: questions that only get asked once we know travel_mode, and only
# for the modes where they're relevant — a public_transport user is never
# asked about fuel brand, since it wouldn't apply to them
CONDITIONAL_QUESTIONS = {
    "own_vehicle": {
        "start_time": "What time do you plan to start driving?",
        "fuel_brand_preferences": "Any preferred fuel station brands? You can name more than one (e.g. HP, Indian Oil) or say no preference.",
    },
}


def next_question(slots: TripSlots) -> Optional[str]:
    for field in REQUIRED_FIELDS:
        # getattr() means result of slots.source/destination/num_days etc
        # since field is the attribute in TripSlots
        if getattr(slots, field) is None:
            return QUESTIONS[field]
    # NEW: once required fields are filled, ask any mode-specific
    # follow-ups relevant to the travel_mode the user picked
    if slots.travel_mode and slots.travel_mode in CONDITIONAL_QUESTIONS:
        for field, question in CONDITIONAL_QUESTIONS[slots.travel_mode].items():
            if getattr(slots, field) is None:
                return question
    return None

    
    