"""
main.py — Smart Parking API + Email Automation
FastAPI backend with MongoDB and event-driven email notifications.

FIXES APPLIED:
  1. Added certifi for SSL certificate verification (fixes MongoDB Atlas SSL error)
  2. Removed unused timedelta import
  3. Added proper scheduler shutdown via app lifespan (prevents zombie threads)
  4. Added .catch() error handlers on all fetch calls in frontend (see index.html)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from pymongo import MongoClient
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from bson import ObjectId
from apscheduler.schedulers.background import BackgroundScheduler
from collections import Counter                      
import os
import re
import threading

from email_service import (
    send_entry_email_user,
    send_entry_email_admin,
    send_exit_email_user,
    send_exit_email_admin,
    send_daily_summary_email,
)

load_dotenv()

PLATE_REGEX = re.compile(r'^[A-Z]{2}\s[0-9]{2}\s[A-Z]{1,3}\s[0-9]{4}$')


# ─── DB helper (FIX 1: use certifi to fix SSL error) ──────────────────────────
def get_db():
    import certifi
    client = MongoClient(
        os.getenv("MONGO_URL"),
        tlsCAFile=certifi.where(),        # ✅ proper SSL via certifi
        serverSelectionTimeoutMS=5000
    )
    db = client["parking"]
    return client,db
# ─── Scheduler (FIX 3: clean shutdown via lifespan) ───────────────────────────
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)      # ← cleanly stop scheduler on server exit

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ───────────────────────────────────────────────────────────────────
class Vehicle(BaseModel):
    name: str
    fee: int
    icon: str
    plate: str
    user_name: str
    user_email: str

    @field_validator('plate')
    @classmethod
    def validate_plate(cls, v):
        val = v.strip().upper()
        if not PLATE_REGEX.match(val):
            raise ValueError('Plate must follow format like KA 40 EK 5158')
        return val


class ExitVehicle(BaseModel):
    id: str


def serialize(doc):
    if doc is None:
        return None
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc


def _calc_duration(entry_str: str, exit_str: str) -> str:
    fmt = "%d-%m-%Y %I:%M %p"
    try:
        entry_dt = datetime.strptime(entry_str, fmt)
        exit_dt  = datetime.strptime(exit_str,  fmt)
        total_minutes = max(int((exit_dt - entry_dt).total_seconds() // 60), 1)
        hours, mins = divmod(total_minutes, 60)
        if hours and mins:
            return f"{hours}h {mins}m"
        elif hours:
            return f"{hours}h"
        else:
            return f"{mins}m"
    except Exception:
        return "N/A"


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "Parking API is running"}


@app.post("/park")
def park_vehicle(v: Vehicle):
    client, db = None, None
    try:
        client, db = get_db()
        vehicles = db["vehicles"]
        logs     = db["logs"]

        if vehicles.find_one({"plate": v.plate}):
            return JSONResponse(status_code=400, content={"error": "Vehicle already parked"})

        time_str = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        result = vehicles.insert_one({
            "name": v.name, "fee": v.fee, "icon": v.icon, "plate": v.plate,
            "user_name": v.user_name, "user_email": v.user_email, "time": time_str,
        })
        logs.insert_one({
            "name": v.name, "icon": v.icon, "plate": v.plate, "fee": v.fee,
            "user_name": v.user_name, "user_email": v.user_email,
            "time": time_str, "type": "in",
        })

        def _send():
            admin_email = os.getenv("ADMIN_EMAIL")
            send_entry_email_user(
                user_email=v.user_email, user_name=v.user_name,
                plate=v.plate, vehicle_type=v.name, icon=v.icon, entry_time=time_str,
            )
            if admin_email:
                send_entry_email_admin(
                    admin_email=admin_email, plate=v.plate, vehicle_type=v.name,
                    icon=v.icon, entry_time=time_str,
                    user_name=v.user_name, user_email=v.user_email,
                )
        threading.Thread(target=_send, daemon=True).start()

        return {"message": "Vehicle parked", "id": str(result.inserted_id)}

    except Exception as e:
        print(f"🔥 ERROR IN /park: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if client: client.close()


@app.post("/exit")
def exit_vehicle(v: ExitVehicle):
    client, db = None, None
    try:
        client, db = get_db()
        vehicles = db["vehicles"]
        logs     = db["logs"]

        vehicle = vehicles.find_one({"_id": ObjectId(v.id)})
        if not vehicle:
            return JSONResponse(status_code=404, content={"error": "Vehicle not found"})

        exit_time  = datetime.now().strftime("%d-%m-%Y %I:%M %p")
        entry_time = vehicle.get("time", exit_time)
        duration   = _calc_duration(entry_time, exit_time)
        fee        = vehicle.get("fee", 0)

        logs.insert_one({
            "name": vehicle["name"], "icon": vehicle["icon"], "plate": vehicle["plate"],
            "fee": fee,
            "user_name": vehicle.get("user_name", ""),
            "user_email": vehicle.get("user_email", ""),
            "time": exit_time, "entry_time": entry_time,
            "duration": duration, "type": "out",
        })
        vehicles.delete_one({"_id": ObjectId(v.id)})

        def _send():
            admin_email  = os.getenv("ADMIN_EMAIL")
            user_email   = vehicle.get("user_email", "")
            user_name    = vehicle.get("user_name", "Guest")
            plate        = vehicle["plate"]
            vehicle_type = vehicle["name"]
            icon         = vehicle["icon"]

            if user_email:
                send_exit_email_user(
                    user_email=user_email, user_name=user_name, plate=plate,
                    vehicle_type=vehicle_type, icon=icon, entry_time=entry_time,
                    exit_time=exit_time, duration=duration, fee=fee, payment_status="Paid",
                )
            if admin_email:
                send_exit_email_admin(
                    admin_email=admin_email, plate=plate, vehicle_type=vehicle_type,
                    icon=icon, entry_time=entry_time, exit_time=exit_time,
                    duration=duration, fee=fee, user_name=user_name, user_email=user_email,
                )
        threading.Thread(target=_send, daemon=True).start()

        return {"message": "Vehicle exited", "duration": duration, "fee": fee}

    except Exception as e:
        print(f"🔥 ERROR IN /exit: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if client: client.close()


@app.get("/data")
def get_data():
    client, db = None, None
    try:
        client, db = get_db()
        parked   = [serialize(v) for v in db["vehicles"].find().sort("_id", -1)]
        log_list = [serialize(l) for l in db["logs"].find().sort("_id", -1).limit(30)]
        count    = len(parked)
        total_result = list(db["logs"].aggregate([
            {"$match": {"type": "in"}},
            {"$group": {"_id": None, "total": {"$sum": "$fee"}}}
        ]))
        amount = total_result[0]["total"] if total_result else 0
        return {"count": count, "amount": amount, "parked": parked, "log": log_list}
    except Exception as e:
        print(f"🔥 ERROR IN /data: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if client: client.close()


@app.post("/reset")
def reset():
    client, db = None, None
    try:
        client, db = get_db()
        db["vehicles"].delete_many({})
        db["logs"].delete_many({})
        return {"message": "All data cleared"}
    except Exception as e:
        print(f"🔥 ERROR IN /reset: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if client: client.close()


@app.get("/email-logs")
def get_email_logs():
    from pathlib import Path
    import json
    log_file = Path("email_records.json")
    if not log_file.exists():
        return {"logs": []}
    try:
        records = json.loads(log_file.read_text())
        return {"logs": records[-50:]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Daily summary job ────────────────────────────────────────────────────────
def _run_daily_summary():
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        return
    client, db = None, None
    try:
        client, db = get_db()
        today_prefix = datetime.now().strftime("%d-%m-%Y")
        today_logs   = list(db["logs"].find({
            "type": "in",
            "time": {"$regex": f"^{today_prefix}"}
        }))
        total_vehicles = len(today_logs)
        total_revenue  = sum(l.get("fee", 0) for l in today_logs)
        hours = [
            datetime.strptime(l["time"], "%d-%m-%Y %I:%M %p").strftime("%I %p")
            for l in today_logs if "time" in l
        ]
        peak_hour = Counter(hours).most_common(1)[0][0] if hours else "N/A"
        breakdown = dict(Counter(l.get("name", "Unknown") for l in today_logs))
        send_daily_summary_email(
            admin_email=admin_email, total_vehicles=total_vehicles,
            total_revenue=total_revenue, peak_hour=peak_hour,
            date_str=today_prefix, vehicle_breakdown=breakdown,
        )
    except Exception as e:
        print(f"[Daily Summary Error] {e}")
    finally:
        if client: client.close()


scheduler.add_job(_run_daily_summary, "cron", hour=23, minute=59)
