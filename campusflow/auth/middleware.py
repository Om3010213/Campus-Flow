import hmac
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from campusflow.product.catalog import ProductError
from .service import resolve, csrf
from .permissions import authorize
from .onboarding import PUBLIC_PATHS
from campusflow.tenancy import institution_context


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        config = request.app.state.security
        path = request.url.path.rstrip("/") or "/"
        # Render's internal load balancer can probe readiness over plain HTTP.
        if request.method == "GET" and path == "/api/ready":
            return await call_next(request)
        if config.production and request.url.scheme != "https":
            return JSONResponse({"status": "error", "message": "HTTPS is required."}, status_code=400)
        if request.method == "OPTIONS" or path == "/api/health":
            return await call_next(request)
        context_token = institution_context.set(None)
        try:
            token = request.cookies.get(config.cookie, "")
            session, user = await run_in_threadpool(resolve, config, token)
            request.state.user, request.state.session, request.state.token = user, session, token
            institution_context.set(user["institution_id"] if user else None)
            public = path in ("/api/auth/session", "/api/auth/login") or path in PUBLIC_PATHS
            if not public and not user:
                raise ProductError("Authentication required. Please sign in.", 401)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and origin not in config.origins:
                    raise ProductError("Untrusted request origin.", 403)
                if not session or not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), csrf(config, token).encode()):
                    raise ProductError("Invalid or missing CSRF token. Refresh and try again.", 403)
            if user and not public:
                if user["must_change_password"] and path not in ("/api/auth/password", "/api/auth/logout"):
                    raise ProductError("Change your temporary password before continuing.", 403)
                if path in ("/docs", "/openapi.json", "/redoc") and user["role"] != "administrator":
                    raise ProductError("Administrator access required.", 403)
                await run_in_threadpool(authorize, user, path, request.method)
            response = await call_next(request)
        except ProductError as exc:
            response = JSONResponse({"status": "error", "message": exc.message, "errors": exc.errors}, status_code=exc.code)
            if exc.code == 429:
                response.headers["Retry-After"] = "900"
        finally:
            institution_context.reset(context_token)
        response.headers["Cache-Control"] = "no-store"
        if response.status_code == 429:
            response.headers["Retry-After"] = "900"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if config.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
