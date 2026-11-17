import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from browser_use import Agent, Browser

load_dotenv(override=True)

app = FastAPI(title="Prispuls AI Agent Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class HuntRequest(BaseModel):
    url: str
    max_price: int
    email: str
    postal_code: str
    card_number: str
    card_expiry: str
    card_cvc: str

@app.post("/api/execute")
async def execute_hunt(request: HuntRequest):
    try:
        # We instruct the agent to handle the screen resolution directly
        task_prompt = f"""
        1. First, resize the browser viewport to 1024x768 to ensure screenshots are small enough for the API proxy.
        2. Go to the product page: {request.url}
        3. Check the price. If it is greater than {request.max_price} SEK, stop immediately and report failure due to price limit.
        4. Accept or close any cookie consent banners.
        5. Click the button to add the item to the cart (Lägg i varukorg / Köp).
        6. Navigate through the slide-out menu to reach the checkout page (Till kassan).
        7. On the checkout page, look for the shipping options. Enter postal code '{request.postal_code}' and email '{request.email}' if required.
        8. Click 'Fortsätt' and select the cheapest shipping option.
        9. Scroll to the payment section (Välj Betalsätt). Select Credit Card (Kort).
        10. Enter Card Number '{request.card_number}', Expiry '{request.card_expiry}', and CVC '{request.card_cvc}' into the payment form.
        11. DO NOT click the final purchase button. Stop here and report success, confirming the payment details were entered.
        """
        
        # 1.0 Syntax: Clean initialization. Headless uses a 1440x900 default, which step 1 overrides.
        browser = Browser('chromium', headless=True)
        
        agent = Agent(
            task=task_prompt,
            llm='anthropic:claude-sonnet-4-5-20250929',
            browser=browser
        )
        
        result = await agent.run()
        
        await browser.close()
        
        return {
            "status": "success", 
            "message": "Agent execution completed.",
            "telemetry": str(result)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))