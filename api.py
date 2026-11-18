import os
import uuid
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from browser_use import Agent, Browser

import stripe_pass

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


class RedeemCodeRequest(BaseModel):
    code: str = Field(min_length=1)


def require_pass_token(x_prispuls_pass: str | None) -> None:
    if not stripe_pass.pass_token_valid(x_prispuls_pass):
        raise HTTPException(status_code=403, detail="Valid Black Friday Pass required")


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


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    if not stripe_pass.webhook_secret():
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_pass.verify_webhook(payload, sig_header)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook") from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") == "paid":
            session_id = session.get("id")
            if session_id:
                stripe_pass.register_paid_session(session_id)
                stripe_pass.grant_pass_for_session(session_id)

    return {"received": True}


@app.get("/api/pass/verify")
async def verify_pass_session(session_id: str):
    token = stripe_pass.grant_pass_for_session(session_id)
    if not token:
        raise HTTPException(status_code=402, detail="Payment not confirmed for this checkout session")
    return {"unlocked": True, "pass_token": token}


@app.get("/api/pass/check")
async def check_pass(x_prispuls_pass: str | None = Header(default=None, alias="X-Prispuls-Pass")):
    return {"unlocked": stripe_pass.pass_token_valid(x_prispuls_pass)}


@app.post("/api/pass/redeem-code")
async def redeem_pass_code(body: RedeemCodeRequest):
    expected = stripe_pass.vip_access_code()
    if not expected or body.code.strip() != expected:
        raise HTTPException(status_code=403, detail="Invalid access code")
    token = stripe_pass.issue_pass_token("vip")
    return {"unlocked": True, "pass_token": token}


@app.post("/api/execute")
async def execute_hunt(
    request: HuntRequest,
    background_tasks: BackgroundTasks,
    x_prispuls_pass: str | None = Header(default=None, alias="X-Prispuls-Pass"),
):
    require_pass_token(x_prispuls_pass)
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