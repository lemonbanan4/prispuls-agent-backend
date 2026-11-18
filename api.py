import os
import uuid
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from browser_use import Agent, Browser

load_dotenv(override=True)

app = FastAPI(title="Prispuls AI Agent Pipeline")

ALLOWED_ORIGINS = [
    "https://pro.prispuls.com",
    "https://prispuls-command-center.vercel.app",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracker — swap for Redis/Firebase in production
jobs = {}


class HuntRequest(BaseModel):
    url: str
    max_price: int
    first_name: str
    last_name: str
    phone: str
    street: str
    postal_code: str
    email: str
    card_number: str
    card_expiry: str
    card_cvc: str


def create_browser() -> Browser:
    if os.getenv("BROWSER_USE_API_KEY"):
        return Browser(live_view=False)
    return Browser("chromium", headless=True)


def extract_telemetry(result) -> str:
    if hasattr(result, "final_result"):
        final = result.final_result()
        if final:
            return final
        text = getattr(result, "text", None)
        if text:
            return text
    return str(result)


async def run_agent_job(job_id: str, request: HuntRequest):
    browser = None
    try:
        jobs[job_id]["telemetry"] = "Browser session starting…"

        task_prompt = f"""
        1. Resize the browser viewport to 1024x768.
        2. Navigate to the product URL: {request.url}
        3. Dismiss any cookie or consent banners (e.g. "Acceptera alla", "Godkänn", "Tillåt alla").
        4. Verify the product is in stock and the price is <= {request.max_price} SEK. If out of stock or over budget, stop immediately and report why.
        5. Add the item to the cart (e.g. "Lägg i varukorg", "Köp", "Lägg till").
        6. Open the cart and proceed to checkout (e.g. "Till kassan", "Gå till kassan"). If prompted to log in, choose guest checkout (e.g. "Fortsätt som gäst", "Handla utan konto").
        7. Enter postal code '{request.postal_code}' and press Enter or blur the field to trigger shipping calculation. Wait for shipping options to load, then select the cheapest home or mailbox delivery option.
        8. Fill customer and shipping fields when requested: First name: {request.first_name}, Last name: {request.last_name}, Phone: {request.phone}, Email: {request.email}, Street: {request.street}.
        9. Advance to payment. Payment UI may be inside Klarna, Briqpay, Walley, Qliro, or Adyen iframes—switch into the correct iframe(s) before interacting with controls.
        10. Select card payment ("Kort" / "Betalkort") and enter card number '{request.card_number}', expiry '{request.card_expiry}', and CVC '{request.card_cvc}'.
        11. STOP before clicking the final purchase or pay button (e.g. "Slutför köp", "Betala"). Confirm payment fields are populated and report success.
        """

        browser = create_browser()

        agent = Agent(
            task=task_prompt,
            llm="google:gemini-2.5-pro",
            browser=browser,
        )

        result = await agent.run()
        jobs[job_id]["status"] = "success"
        jobs[job_id]["telemetry"] = extract_telemetry(result)

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["telemetry"] = str(e)

    finally:
        if browser:
            await browser.close()


@app.post("/api/execute")
async def execute_hunt(request: HuntRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "queued",
        "telemetry": "Job queued. Initializing browser session…",
    }
    background_tasks.add_task(run_agent_job, job_id, request)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]