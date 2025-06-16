from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from browser_use import Agent, BrowserSession
from dotenv import load_dotenv
load_dotenv()

import asyncio

llm = ChatOpenAI(model="gpt-4o")
# llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')

# If no executable_path provided, uses Playwright/Patchright's built-in Chromium
browser_session = BrowserSession(
    # Path to a specific Chromium-based executable (optional)
    executable_path='/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',  # macOS
    # Use a specific data directory on disk (optional, set to None for incognito)
    user_data_dir=None # '~/.config/browseruse/profiles/default',   # this is the default
    # ... any other BrowserProfile or playwright launch_persistnet_context config...
    # headless=False,
)
async def main():
    agent = Agent(
        task="Find me and return the link to the men's running shoe with the most ratings on Amazon.", # "Where (channel) and when can I watch the next game of the NBA finals. Which game is it?",
        llm=llm,
        browser_session=browser_session,
    )
    result = await agent.run()
    print(result)

asyncio.run(main())