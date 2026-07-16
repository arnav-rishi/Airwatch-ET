from dotenv import load_dotenv

# services/llm.py constructs an AzureOpenAI client at import time, which raises
# immediately if AZURE_OPENAI_API_KEY etc. aren't set. main.py loads .env before
# importing routes; pytest never goes through main.py, so tests that transitively
# import services.llm need the same bootstrap here.
load_dotenv(override=True)
