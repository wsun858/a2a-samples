from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from browser_use import Agent, BrowserSession
from dotenv import load_dotenv
load_dotenv()

import asyncio

llm = ChatOpenAI(model="gpt-4o")
# llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')

browser_session = BrowserSession(
    # Path to a specific Chromium-based executable (optional)
    executable_path='/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    # Use a specific data directory on disk (optional, set to None for incognito)
    user_data_dir=None # '~/.config/browseruse/profiles/default',   # this is the default
)
async def main():
    agent = Agent(
        task="Demonstrate your captcha solving ability by opening this website and solving the puzzle (https://2captcha.com/demo/normal)", # "Use a free online pdf splitting website to split the pdf at ~/Desktop/barfoot_ser17.pdf into two halves. Download files to ~/Desktop", # "Find me and return the link to the men's running shoe with the most ratings on Amazon.", # "Where (channel) and when can I watch the next game of the NBA finals. Which game is it?",
        llm=llm,
        browser_session=browser_session,
    )
    result = await agent.run()
    print(result)

asyncio.run(main())