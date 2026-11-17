import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from browser_use import Agent, Browser

# Force system to use your .env file
load_dotenv(override=True)

app = FastAPI(title="Prispuls AI Agent Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The data payload from Next.js
class HuntRequest(BaseModel):
    url: str
    max_price: int
    email: str
    postal_code: str

@app.post("/api/execute")
async def execute_hunt(request: HuntRequest):
    try:
        # Dynamic prompt injecting user context to bypass the shipping gotcha
        task_prompt = f"""
        1. Go to the product page: {request.url}
        2. Check the price. If it is greater than {request.max_price} SEK, stop immediately and report failure due to price limit.
        3. Accept or close any cookie consent banners.
        4. Click the button to add the item to the cart (Lägg i varukorg / Köp).
        5. Navigate through the slide-out menu to reach the checkout page (Till kassan).
        6. On the checkout page, look for the shipping options (Leveranssätt / Fraktsätt). If the site requires a postal code to calculate shipping, enter '{request.postal_code}'.
        7. If asked for an email for a guest checkout, enter '{request.email}'.
        8. Click 'Fortsätt' to unlock the shipping options.
        9. Stop and report success once shipping options are fully visible and the next step is unlocked.
        """

        agent = Agent(
            task=task_prompt,
            llm="anthropic:claude-sonnet-4-5-20250929",
            browser=Browser('chromium')
        )

        result = await agent.run()

        # Return the final agent log to the frontend
        return {
            "status": "success",
            "message": "Agent execution completed.",
            "telemetry": str(result)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
