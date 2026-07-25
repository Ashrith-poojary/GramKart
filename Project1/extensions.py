from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_caching import Cache
from flask_migrate import Migrate

# Instantiate shared extensions
db = SQLAlchemy()
csrf = CSRFProtect()
mail = Mail()
cache = Cache()
migrate = Migrate()

from flask_socketio import SocketIO

# Instantiate rate limiter with client IP remote address as default key
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Instantiate SocketIO extension
socketio = SocketIO(cors_allowed_origins="*")
