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
        3. Check the price. If it is greater than {request.max_price} SEK, stop immediately and report failure.
        4. Accept or close any cookie consent banners.
        5. Click the button to add the item to the cart (Lägg i varukorg).
        6. Navigate through the slide-out menu to reach the checkout page (Till kassan).
        7. On the checkout page, locate the postal code field. Enter '{request.postal_code}'. 
        8. CRITICAL: After typing the postal code, press the 'Enter' key or click on the background of the page to trigger the website's shipping calculation API. Do NOT force the Fortsätt button. Wait for the shipping options to load natively, then select the cheapest one and click Fortsätt.
        9. In the Customer Information (Kundinformation) section, fill in the following details to unlock the payment module:
           - First Name: Liam
           - Last Name: Högberg
           - Phone: 0701234567
           - Email: {request.email}
        10. Click Fortsätt to reach the payment section (Välj Betalsätt). Wait for the payment options to fully render.
        11. Select Credit Card (Kort). Enter Card Number '{request.card_number}', Expiry '{request.card_expiry}', and CVC '{request.card_cvc}'.
        12. DO NOT click the final purchase button. Stop here and report success.
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