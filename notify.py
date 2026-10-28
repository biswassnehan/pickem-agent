"""
Emails the weekly brief using a Gmail app password.

Optional. If the Secrets below aren't set, the brief is just printed.
  GMAIL_ADDRESS       your Gmail address
  GMAIL_APP_PASSWORD  a 16-character app password (not your normal password)
  EMAIL_TO            where to send it (defaults to GMAIL_ADDRESS)
"""

import os
import smtplib
from email.message import EmailMessage


def send_email(subject, body):
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not (sender and password):
        print("(Email not configured - skipping send.)")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = os.environ.get("EMAIL_TO", sender)
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print(f"Emailed brief to {msg['To']}")
