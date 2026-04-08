"""
email_service.py — Smart Parking Email Automation Module

FIXES APPLIED:
  1. Added threading.Lock on JSON log file (fixes race condition with concurrent emails)
  2. Removed emoji from SMTP From header (fixes delivery issues on strict SMTP servers)
  3. Cleaned up From header encoding to be RFC-compliant
"""

import smtplib
import os
import json
import time
import logging
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("email_log.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── Thread-safe email log (FIX 1) ────────────────────────────────────────────
EMAIL_LOG_FILE = Path("email_records.json")
_log_lock = threading.Lock()           # ← prevents race condition on concurrent writes

def _append_email_log(record: dict):
    with _log_lock:                    # ← only one thread writes at a time
        records = []
        if EMAIL_LOG_FILE.exists():
            try:
                records = json.loads(EMAIL_LOG_FILE.read_text())
            except Exception:
                records = []
        records.append(record)
        EMAIL_LOG_FILE.write_text(json.dumps(records, indent=2))


# ─── Core SMTP sender with retry ──────────────────────────────────────────────
def _send_email(to: str, subject: str, html_body: str, retries: int = 3) -> bool:
    smtp_host    = "smtp.gmail.com"
    smtp_port    = 587
    sender_email = os.getenv("EMAIL_SENDER")
    sender_pass  = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_pass:
        logger.error("EMAIL_SENDER / EMAIL_PASSWORD not set in .env — skipping email")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Smart Parking <{sender_email}>"   # FIX 2: no emoji in From header
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html"))

    for attempt in range(1, retries + 1):
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls()
                server.login(sender_email, sender_pass)
                server.sendmail(sender_email, to, msg.as_string())

            logger.info(f"Email sent to {to} | {subject}")
            _append_email_log({
                "timestamp": datetime.now().isoformat(),
                "to": to, "subject": subject, "status": "sent"
            })
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP auth failed — check EMAIL_SENDER / EMAIL_PASSWORD")
            _append_email_log({
                "timestamp": datetime.now().isoformat(),
                "to": to, "subject": subject, "status": "auth_error"
            })
            return False   # no point retrying auth errors

        except Exception as e:
            logger.warning(f"Attempt {attempt}/{retries} failed for {to}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)   # 2s, 4s backoff

    _append_email_log({
        "timestamp": datetime.now().isoformat(),
        "to": to, "subject": subject, "status": "failed_after_retries"
    })
    logger.error(f"All {retries} attempts failed for {to}")
    return False


# ─── Shared HTML shell ─────────────────────────────────────────────────────────
def _wrap_html(content: str, title: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0f;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#111118;border:1px solid #2a2a3a;border-radius:12px;overflow:hidden;max-width:600px;width:100%;">
        <tr>
          <td style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:32px 40px;text-align:center;border-bottom:1px solid #2a2a3a;">
            <div style="font-size:36px;margin-bottom:8px;">&#x1F17F;&#xFE0F;</div>
            <h1 style="margin:0;color:#f5c542;font-size:26px;font-weight:800;letter-spacing:4px;text-transform:uppercase;">Smart Parking</h1>
            <p style="margin:4px 0 0;color:#6b6b88;font-size:11px;letter-spacing:3px;text-transform:uppercase;">Automated Notification System</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px;">{content}</td>
        </tr>
        <tr>
          <td style="background:#0d0d14;border-top:1px solid #2a2a3a;padding:20px 40px;text-align:center;">
            <p style="margin:0;color:#3b3b55;font-size:11px;letter-spacing:1px;">
              &copy; {datetime.now().year} Smart Parking Management System &nbsp;|&nbsp; Automated email
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _info_row(label: str, value: str, accent: bool = False) -> str:
    color = "#f5c542" if accent else "#e8e8f0"
    return f"""
    <tr>
      <td style="padding:10px 0;border-bottom:1px solid #1e1e2d;">
        <span style="color:#6b6b88;font-size:12px;text-transform:uppercase;letter-spacing:1px;">{label}</span>
      </td>
      <td style="padding:10px 0;border-bottom:1px solid #1e1e2d;text-align:right;">
        <strong style="color:{color};font-size:14px;">{value}</strong>
      </td>
    </tr>"""


# ─── 1. Vehicle Entry Email (User) ────────────────────────────────────────────
def send_entry_email_user(
    user_email: str, user_name: str, plate: str,
    vehicle_type: str, icon: str, entry_time: str,
    location: str = "Block A, Level 1"
) -> bool:
    content = f"""
    <p style="color:#f5c542;font-size:22px;font-weight:700;margin:0 0 6px;">Welcome, {user_name}!</p>
    <p style="color:#6b6b88;font-size:13px;margin:0 0 28px;">Your vehicle has been successfully registered. Keep this receipt for your records.</p>
    <div style="background:rgba(61,255,160,0.08);border:1px solid rgba(61,255,160,0.25);border-radius:8px;padding:16px 20px;text-align:center;margin-bottom:28px;">
      <span style="color:#3dffa0;font-size:13px;font-weight:600;letter-spacing:2px;text-transform:uppercase;">&#x2705; &nbsp; Vehicle Parked Successfully</span>
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      {_info_row("Vehicle Number", plate, accent=True)}
      {_info_row("Vehicle Type", f"{icon} {vehicle_type}")}
      {_info_row("Entry Time", entry_time)}
      {_info_row("Parking Location", location)}
    </table>
    <div style="background:#16161f;border-left:3px solid #f5c542;border-radius:0 6px 6px 0;padding:16px 20px;">
      <p style="margin:0;color:#b0b0c8;font-size:13px;line-height:1.7;">
        &#x1F514; <strong style="color:#e8e8f0;">Reminder:</strong> Please collect your vehicle before midnight
        to avoid overnight charges. Billing starts from entry time.
      </p>
    </div>"""
    return _send_email(user_email, f"Vehicle Parked - {plate}", _wrap_html(content, "Parking Entry"))


# ─── 2. Vehicle Exit Email (User) ────────────────────────────────────────────
def send_exit_email_user(
    user_email: str, user_name: str, plate: str, vehicle_type: str,
    icon: str, entry_time: str, exit_time: str, duration: str,
    fee: int, payment_status: str = "Paid"
) -> bool:
    paid = payment_status == "Paid"
    content = f"""
    <p style="color:#f5c542;font-size:22px;font-weight:700;margin:0 0 6px;">Safe travels, {user_name}!</p>
    <p style="color:#6b6b88;font-size:13px;margin:0 0 28px;">Your parking session has ended. Here is your exit summary and billing receipt.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      {_info_row("Vehicle Number", plate, accent=True)}
      {_info_row("Vehicle Type", f"{icon} {vehicle_type}")}
      {_info_row("Entry Time", entry_time)}
      {_info_row("Exit Time", exit_time)}
      {_info_row("Total Duration", duration)}
    </table>
    <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #2a2a3a;border-radius:10px;padding:24px;text-align:center;margin-bottom:24px;">
      <p style="margin:0 0 4px;color:#6b6b88;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Total Amount</p>
      <p style="margin:0 0 12px;color:#f5c542;font-size:42px;font-weight:800;">&#x20B9;{fee:,}</p>
      <span style="background:{'rgba(61,255,160,0.15)' if paid else 'rgba(255,94,58,0.15)'};
                   color:{'#3dffa0' if paid else '#ff5e3a'};
                   border:1px solid {'rgba(61,255,160,0.4)' if paid else 'rgba(255,94,58,0.4)'};
                   border-radius:20px;padding:6px 18px;font-size:12px;font-weight:600;">
        {payment_status}
      </span>
    </div>
    <p style="margin:0;color:#6b6b88;font-size:12px;text-align:center;">Thank you for using Smart Parking!</p>"""
    return _send_email(user_email, f"Exit Receipt - {plate} | Rs.{fee:,}", _wrap_html(content, "Exit Summary"))


# ─── 3. Admin Entry Notification ─────────────────────────────────────────────
def send_entry_email_admin(
    admin_email: str, plate: str, vehicle_type: str, icon: str,
    entry_time: str, user_name: str, user_email: str, slot: str = "Auto-assigned"
) -> bool:
    content = f"""
    <p style="color:#f5c542;font-size:18px;font-weight:700;margin:0 0 6px;">New Vehicle Entry</p>
    <p style="color:#6b6b88;font-size:13px;margin:0 0 24px;">A vehicle has just entered the parking facility.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      {_info_row("Vehicle Number", plate, accent=True)}
      {_info_row("Vehicle Type", f"{icon} {vehicle_type}")}
      {_info_row("Entry Time", entry_time)}
      {_info_row("Slot / Area", slot)}
      {_info_row("Owner Name", user_name)}
      {_info_row("Owner Email", user_email)}
    </table>"""
    return _send_email(admin_email, f"[ENTRY] {plate} - {entry_time}", _wrap_html(content, "Admin Entry"))


# ─── 4. Admin Exit Notification ──────────────────────────────────────────────
def send_exit_email_admin(
    admin_email: str, plate: str, vehicle_type: str, icon: str,
    entry_time: str, exit_time: str, duration: str,
    fee: int, user_name: str, user_email: str
) -> bool:
    content = f"""
    <p style="color:#ff5e3a;font-size:18px;font-weight:700;margin:0 0 6px;">Vehicle Exit - Revenue Collected</p>
    <p style="color:#6b6b88;font-size:13px;margin:0 0 24px;">A vehicle has exited. Billing summary below.</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      {_info_row("Vehicle Number", plate, accent=True)}
      {_info_row("Vehicle Type", f"{icon} {vehicle_type}")}
      {_info_row("Owner", user_name)}
      {_info_row("Entry Time", entry_time)}
      {_info_row("Exit Time", exit_time)}
      {_info_row("Duration", duration)}
      {_info_row("Fee Collected", f"Rs.{fee:,}", accent=True)}
    </table>"""
    return _send_email(admin_email, f"[EXIT] {plate} | Rs.{fee:,} collected", _wrap_html(content, "Admin Exit"))


# ─── 5. Daily Revenue Summary ─────────────────────────────────────────────────
def send_daily_summary_email(
    admin_email: str, total_vehicles: int, total_revenue: int,
    peak_hour: str, date_str: str, vehicle_breakdown: dict
) -> bool:
    rows = "".join(_info_row(vtype, f"{cnt} vehicles") for vtype, cnt in vehicle_breakdown.items())
    content = f"""
    <p style="color:#f5c542;font-size:18px;font-weight:700;margin:0 0 6px;">Daily Revenue Report</p>
    <p style="color:#6b6b88;font-size:13px;margin:0 0 24px;">End-of-day summary for <strong style="color:#e8e8f0;">{date_str}</strong></p>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr>
        <td width="50%" style="padding:0 8px 0 0;">
          <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #2a2a3a;border-radius:10px;padding:20px;text-align:center;">
            <p style="margin:0 0 4px;color:#6b6b88;font-size:10px;letter-spacing:2px;text-transform:uppercase;">Total Vehicles</p>
            <p style="margin:0;color:#f5c542;font-size:34px;font-weight:800;">{total_vehicles}</p>
          </div>
        </td>
        <td width="50%" style="padding:0 0 0 8px;">
          <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #2a2a3a;border-radius:10px;padding:20px;text-align:center;">
            <p style="margin:0 0 4px;color:#6b6b88;font-size:10px;letter-spacing:2px;text-transform:uppercase;">Total Revenue</p>
            <p style="margin:0;color:#3dffa0;font-size:34px;font-weight:800;">&#x20B9;{total_revenue:,}</p>
          </div>
        </td>
      </tr>
    </table>
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
      {_info_row("Peak Hour", peak_hour, accent=True)}
      {rows}
    </table>"""
    return _send_email(
        admin_email,
        f"Daily Summary - {date_str} | Rs.{total_revenue:,} revenue",
        _wrap_html(content, "Daily Revenue Summary")
    )
