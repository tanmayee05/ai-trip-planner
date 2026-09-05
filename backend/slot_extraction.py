import os
from dotenv import load_dotenv
import time
from google.genai.errors import ClientError
from langchain_google_genai import ChatGoogleGenerativeAI
from trip_slots import TripSlots

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# One LLM, configured once. `.with_structured_output(TripSlots)` makes the model
# return a validated TripSlots object directly — no "reply with JSON" instruction,
# no ```json fences to strip, no json.loads(). LangChain drives Gemini's
# function-calling / JSON-schema mode from the Pydantic model itself.
llm = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=os.getenv("GEMINI_API_KEY"),
)
extractor = llm.with_structured_output(TripSlots)

EXTRACTION_PROMPT = """You extract trip-planning details from a user's message.
You will also be told what question was just asked, if any — use that context
to interpret short answers correctly. For example, if asked "Where are you
starting from?" and the user replies "guntur", that means source = "guntur".

Only fill fields that are explicitly stated or clearly implied by the question
context. Leave every other field null — do not guess unrelated fields.

Note: fuel_brand_preference and start_time only make sense if the user is
travelling by own_vehicle — don't fill them from unrelated context, only
when the user is actually answering a question about driving/fuel/departure time.
"""


def extract_new_info(user_message: str, last_question: str | None = None) -> dict:
    """Ask the model what NEW info is in this one message, given what was just asked.
    
        Returns a plain dict containing only the fields the model actually filled.
        """
    context = f'The question just asked was: "{last_question}"\n' if last_question else ""
    human = f'{context}User message: "{user_message}"'

    for attempt in range(3):
        try:
            result: TripSlots = extractor.invoke(
                [
                    ("system", EXTRACTION_PROMPT),
                    ("human", human),
                ]
            )
            # Keep only the fields the model populated so a merge never wipes known slots.
            return result.model_dump(exclude_none=True)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60 * (attempt + 1)
                print(f"Rate limit hit — waiting {wait}s before retrying...")
                time.sleep(wait)
            else:
                raise  # a real error, not a rate limit — don't hide it

    print("Still rate-limited after retries — please try again in a minute.")
    return {}


def update_slots(
    current_slots: TripSlots,
    user_message: str,
    last_question: str | None = None,
) -> TripSlots:
    """Extract new info (using question context) and merge it into existing slots."""
    new_info = extract_new_info(user_message, last_question)
    updated = current_slots.model_copy(update=new_info)
    return updated


if __name__ == "__main__":
    from trip_slots import TripSlots
    from slot_extraction import update_slots

    slots = TripSlots()
    slots = update_slots(slots, "own vehicle", last_question="Will you travel by your own vehicle, or public transport?")
    print(slots)

    slots = update_slots(slots, "6am", last_question="What time do you plan to start driving?")
    print(slots)

    slots = update_slots(slots, "I like HP stations", last_question="Do you have a preferred fuel station brand?")
    print(slots)
    slots = TripSlots()
    slots = update_slots(slots, "5 days trip to Coorg")
    print(slots)

    slots = update_slots(slots, "starting from Rebala")
    print(slots)