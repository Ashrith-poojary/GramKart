import threading
from flask import current_app
from flask_mail import Message
from extensions import mail

def send_async_email(app, msg):
    """Worker function to send mail asynchronously using app context."""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Async email sending failed: {e}")

def send_email(subject, recipients, html_body):
    """Enqueues and sends an email in a background daemon thread."""
    app = current_app._get_current_object()
    
    msg = Message(
        subject=subject,
        recipients=recipients,
        html=html_body,
        sender=app.config.get('MAIL_DEFAULT_SENDER')
    )
    
    # Threaded delivery to avoid blocking requests (prepares for Celery Integration)
    thread = threading.Thread(target=send_async_email, args=(app, msg))
    thread.daemon = True
    thread.start()
    return thread

def send_order_confirmation(recipient_email, customer_name, order_id, total):
    """Trigger order placement receipt mail."""
    subject = f"Order #{order_id} Confirmed - GramKart"
    body = f"<h3>Hi {customer_name},</h3><p>Your order #{order_id} for a total of ₹{total} was placed successfully.</p>"
    return send_email(subject, [recipient_email], body)

def send_password_reset_alert(recipient_email, reset_link):
    """Trigger account security reset notification."""
    subject = "Password Reset Link - GramKart"
    body = f"<h3>Reset Password</h3><p>Please use this link to reset your password: <a href='{reset_link}'>{reset_link}</a></p>"
    return send_email(subject, [recipient_email], body)
