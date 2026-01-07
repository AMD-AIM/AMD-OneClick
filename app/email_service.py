"""
Email service for sending notebook URLs
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


def send_notebook_url_email(email: str, notebook_url: str) -> bool:
    """Send notebook URL to user via email"""
    
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning("SMTP not configured, skipping email send")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Your AMD OneClick Notebook is Ready'
        msg['From'] = settings.SMTP_FROM
        msg['To'] = email
        
        text_content = f"""
Your AMD OneClick Notebook is Ready!

Access your Jupyter Notebook at:
{notebook_url}

Note: This notebook instance will be automatically destroyed after {settings.MAX_LIFETIME_HOURS} hours 
or after {settings.IDLE_TIMEOUT_MINUTES} minutes of inactivity.

Happy coding!
AMD OneClick Team
"""
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #ed1c24, #000); color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background: #f9f9f9; }}
        .button {{ display: inline-block; padding: 12px 24px; background: #ed1c24; color: white; 
                   text-decoration: none; border-radius: 4px; margin: 20px 0; }}
        .footer {{ padding: 20px; text-align: center; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Your Notebook is Ready!</h1>
        </div>
        <div class="content">
            <p>Hi there!</p>
            <p>Your AMD OneClick Jupyter Notebook has been created and is ready to use.</p>
            <p style="text-align: center;">
                <a href="{notebook_url}" class="button">Open Notebook</a>
            </p>
            <p><strong>Direct URL:</strong><br>
            <a href="{notebook_url}">{notebook_url}</a></p>
            <p><strong>Important:</strong></p>
            <ul>
                <li>Maximum session time: {settings.MAX_LIFETIME_HOURS} hours</li>
                <li>Auto-shutdown after {settings.IDLE_TIMEOUT_MINUTES} minutes of inactivity</li>
            </ul>
        </div>
        <div class="footer">
            <p>AMD OneClick Notebook Manager</p>
        </div>
    </div>
</body>
</html>
"""
        
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Sent notebook URL email to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        return False
