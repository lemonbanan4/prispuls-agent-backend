import os
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
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

# In-memory job tracker — swap for Redis/Firebase in production
jobs = {}

class HuntRequest(BaseModel):
    url: str
    max_price: int
    email: str
    postal_code: str
    card_number: str
    card_expiry: str
    card_cvc: str

async def run_agent_job(job_id: str, request: HuntRequest):
    browser = None
    try:
        task_prompt = f"""
        1. Resize the browser viewport to 1024x768.
        2. Navigate to the product URL: {request.url}
        3. Dismiss any cookie consent banners ("Acceptera alla", "Godkänn", "Tillåt alla").
        4. Verify the product is in stock and the price is <= {request.max_price} SEK. If out of stock or over budget, stop immediately and report why.
        5. Add the item to the cart ("Lägg i varukorg", "Köp", "Lägg till").
        6. Open the cart and proceed to checkout ("Till kassan", "Gå till kassan"). If prompted to log in, always choose Guest Checkout ("Fortsätt som gäst", "Handla utan konto").
        7. Enter postal code '{request.postal_code}' and press 'Enter' or click outside the field to trigger shipping calculation. Wait for shipping options to load natively, then select the cheapest home/mailbox delivery option.
        8. Fill customer details if requested: First Name: Liam, Last Name: Högberg, Phone: 0701234567, Email: {request.email}, Street: Kungsgatan 1.
        9. Advance to the payment section (may be embedded inside a Klarna, Briqpay, Walley, Qliro, or Adyen iframe).
        10. Select Card payment ("Kort" / "Betalkort") and enter Card Number '{request.card_number}', Expiry '{request.card_expiry}', and CVC '{request.card_cvc}'.
        11. STOP before clicking the final purchase/pay button ("Slutför köp" / "Betala"). Confirm the payment fields are populated and report success.
        """

        browser = Browser('chromium', headless=True)

        agent = Agent(
            task=task_prompt,
            #llm='anthropic:claude-sonnet-4-5-20250929',
            llm='google:gemini-3.8-flash',
            browser=browser
        )

        result = await agent.run()
        jobs[job_id]["status"] = "success"
        jobs[job_id]["telemetry"] = str(result)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["telemetry"] = str(e)

    finally:
        if browser:
            await browser.close()

@app.post("/api/execute")
async def execute_hunt(request: HuntRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "telemetry": "Job queued. Initializing headless Chromium..."}
    background_tasks.add_task(run_agent_job, job_id, request)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
