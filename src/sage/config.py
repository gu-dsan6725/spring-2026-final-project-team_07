from dotenv import load_dotenv
import os

load_dotenv()

NARRATOR_MODEL = os.getenv("NARRATOR_MODEL", "groq/llama-3.1-8b-instant")
NARRATOR_TEMPERATURE = float(os.getenv("NARRATOR_TEMPERATURE", "0.7"))
NARRATOR_MAX_TOKENS = int(os.getenv("NARRATOR_MAX_TOKENS", "512"))
