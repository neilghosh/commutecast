import firebase_admin
from firebase_admin import auth, credentials
from firebase_functions import https_fn
import functools

# Initialize firebase-admin only once
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app()

def authenticated(func):
    """Decorator to verify Firebase ID Token in the Authorization header."""
    @functools.wraps(func)
    def wrapper(req: https_fn.Request) -> https_fn.Response:
        # Allow OPTIONS requests to pass through without authentication for CORS
        if req.method == "OPTIONS":
            return func(req)

        auth_header = req.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return https_fn.Response("Unauthorized: Missing or invalid token", status=401)
        
        id_token = auth_header.split("Bearer ")[1]
        try:
            decoded_token = auth.verify_id_token(id_token)
            req.auth = decoded_token  # Attach decoded token to request
            return func(req)
        except Exception as e:
            return https_fn.Response(f"Unauthorized: {str(e)}", status=401)
            
    return wrapper

def admin_only(func):
    """Decorator to verify if the authenticated user has an admin role."""
    @functools.wraps(func)
    @authenticated
    def wrapper(req: https_fn.Request) -> https_fn.Response:
        if not req.auth.get("admin", False):
            return https_fn.Response("Forbidden: Admin access required", status=403)
        return func(req)
    return wrapper
