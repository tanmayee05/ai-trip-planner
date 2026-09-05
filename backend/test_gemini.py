import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load .env so we can read GEMINI_API_KEY
load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

response = llm.invoke("Say hello in one short sentence.")

print(response.content)
