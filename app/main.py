from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError, AuthenticationError, TooManyRequestsError


async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    headers: dict[str, str] = {}
    if isinstance(exc, AuthenticationError):
        headers["WWW-Authenticate"] = "Bearer"
    if isinstance(exc, TooManyRequestsError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
        headers=headers,
    )


def _mark_binary_fields(node: object) -> None:
    """OpenAPI 3.1 describes uploads as {"contentMediaType": "application/octet-stream"}, which
    Swagger UI renders as a *text* box for arrays of files. Adding format=binary makes it show
    a file picker again. Only the generated docs change; request handling is unaffected."""
    if isinstance(node, dict):
        if node.get("contentMediaType") == "application/octet-stream":
            node.setdefault("format", "binary")
        for value in node.values():
            _mark_binary_fields(value)
    elif isinstance(node, list):
        for value in node:
            _mark_binary_fields(value)


def _install_openapi_fix(app: FastAPI) -> None:
    original = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is None:
            schema = original()
            _mark_binary_fields(schema)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        swagger_ui_parameters={
            "tryItOutEnabled": True,       # show Execute directly, no "Try it out" click
            "persistAuthorization": True,  # keep the Authorize token across page reloads
        },
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_exception_handler(AppError, handle_app_error)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    _install_openapi_fix(app)

    if settings.app_env != "production":
        # Local storage backend: serve uploaded files directly. In production a CDN/S3
        # (or nginx) serves media and MEDIA_BASE_URL points there instead.
        media_dir = Path(settings.media_root)
        media_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=media_dir), name="media")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    return app


app = create_app()
