import os
from flask import current_app

def send_sms_notification(phone_number, message):
    """
    Sends an SMS notification using Twilio client if configured,
    otherwise logs the SMS details to the application logger.
    """
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_phone = current_app.config.get('TWILIO_PHONE_NUMBER')
    
    if account_sid and auth_token and from_phone:
        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=message,
                from_=from_phone,
                to=phone_number
            )
            current_app.logger.info(f"Twilio SMS sent to {phone_number}: {message}")
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to send Twilio SMS to {phone_number}: {e}")
            return False
    else:
        current_app.logger.info(f"[SMS MOCK] Simulated SMS to {phone_number}: {message}")
        return True
