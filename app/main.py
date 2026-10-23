from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, catalog, catalog_admin, comparison, emails, health, providers, quotes, solicitudes, smtp_account
from app.core.config import get_settings
from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.models.domain import LocalUser
from app.services.auth import parse_session_token

settings = get_settings()
ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        init_database(seed=settings.seed_on_startup)
    yield


docs_url = "/docs" if settings.enable_docs else None
redoc_url = "/redoc" if settings.enable_docs else None
openapi_url = "/openapi.json" if settings.enable_docs else None

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=600)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

PUBLIC_PATHS = {
    "/login",
    "/health",
    "/health/ready",
    "/api/auth/login",
}


def _request_user(request: Request) -> LocalUser | None:
    if not settings.auth_enabled:
        return None
    identity = parse_session_token(
        request.cookies.get(settings.session_cookie_name),
        settings.session_secret,
    )
    if not identity:
        return None
    with SessionLocal() as db:
        user = db.get(LocalUser, identity.user_id)
        if not user or not user.active or user.username != identity.username:
            return None
        db.expunge(user)
        return user


@app.middleware("http")
async def authentication_guard(request: Request, call_next):
    path = request.url.path
    if not settings.auth_enabled or path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    user = _request_user(request)
    if user:
        request.state.user = user
        if path == "/login":
            return RedirectResponse(url="/", status_code=303)
        return await call_next(request)

    if path.startswith("/api/") or path in {"/openapi.json"}:
        return JSONResponse(status_code=401, content={"detail": "Autenticación requerida"})
    return RedirectResponse(url="/login", status_code=303)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=300"
    return response


app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(smtp_account.router, prefix="/api")
app.include_router(solicitudes.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(emails.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(catalog_admin.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(comparison.router, prefix="/api")

app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if settings.auth_enabled and _request_user(request):
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(ROOT / "frontend" / "login.html")


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(ROOT / "frontend" / "index.html")
