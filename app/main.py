from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

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

    if settings.app_env != "production":
        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    return app


app = create_app()
