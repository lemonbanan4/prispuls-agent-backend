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

# Added payment fields to the payload
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
        # The ultimate autonomous prompt
        task_prompt = f"""
        1. Go to the product page: {request.url}
        2. Check the price. If it is greater than {request.max_price} SEK, stop immediately and report failure due to price limit.
        3. Accept or close any cookie consent banners.
        4. Click the button to add the item to the cart (Lägg i varukorg / Köp).
        5. Navigate through the slide-out menu to reach the checkout page (Till kassan).
        6. On the checkout page, look for the shipping options. Enter postal code '{request.postal_code}' and email '{request.email}' if required.
        7. Click 'Fortsätt' and select the cheapest shipping option.
        8. Scroll to the payment section (Välj Betalsätt). Select Credit Card (Kort).
        9. Enter Card Number '{request.card_number}', Expiry '{request.card_expiry}', and CVC '{request.card_cvc}' into the payment form.
        10. DO NOT click the final purchase button. Stop here and report success, confirming the payment details were entered.
        """
        
        # FIX: The exact, correct Claude 3.5 model string
        agent = Agent(
            task=task_prompt,
            llm='anthropic:claude-3-5-sonnet-20241022',
            browser=Browser('chromium')
        )
        
        result = await agent.run()
        
        return {
            "status": "success", 
            "message": "Agent execution completed.",
            "telemetry": str(result)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))