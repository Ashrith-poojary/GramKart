import os
import uuid
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.utils import secure_filename
from PIL import Image

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    """Verify file name extensions match allowed list."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_and_optimize_image(file, upload_folder, max_width=800, max_height=800):
    """Securely save an uploaded image file, renaming and compressing it."""
    if not file or not allowed_file(file.filename):
        return None
        
    filename = secure_filename(file.filename)
    # Generate random unique filename to prevent overwrites / predictable names
    ext = filename.rsplit('.', 1)[1].lower()
    random_name = f"{uuid.uuid4().hex}.{ext}"
    
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, random_name)
    
    # Save and crop/compress using Pillow
    try:
        img = Image.open(file)
        # Convert RGBA to RGB if saving as JPEG
        if img.mode in ('RGBA', 'LA') and ext in ('jpg', 'jpeg'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3]) # 3 is the alpha channel
            img = background
            
        img.thumbnail((max_width, max_height))
        img.save(filepath, optimize=True, quality=85)
        
        # Return public relative path
        return f"/static/uploads/{random_name}"
    except Exception as e:
        print("Image optimization failed:", e)
        return None

def setup_logger(app):
    """Configure rotating log handler for server warnings and auth audits."""
    log_dir = os.path.join(app.root_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'gramkart.log')
    
    # Max size 5MB per file, rotating up to 5 backfiles
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
    file_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s [%(ip)s]: %(message)s'
    )
    file_handler.setFormatter(formatter)
    
    # Inject client IP address into logs filter context
    class ContextFilter(logging.Filter):
        def filter(self, record):
            from flask import request
            record.ip = request.remote_addr if request else 'system'
            return True
            
    file_handler.addFilter(ContextFilter())
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
