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
