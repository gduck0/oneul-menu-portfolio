from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.food_api import router as food_router
from app.account_api import router as account_router
from app.preference_api import router as preference_router
from app.planner_api import router as planner_router
from app.runtime import application_origins
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(title="오늘 뭐 먹지?", version="0.1.0")
app.include_router(food_router)
app.include_router(account_router)
app.include_router(preference_router)
app.include_router(planner_router)


@app.middleware('http')
async def check_origin(request, call_next):
    if request.url.path.startswith('/api/') and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        allowed = application_origins()
        if (origin and origin not in allowed) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse(status_code=403, content={'detail': '요청 출처를 확인하지 못했어요.'})
        if request.method != 'DELETE' and request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse(status_code=415, content={'detail': '지원하지 않는 요청 형식이에요.'})
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(RequestValidationError)
def input_error(request, error):
    return JSONResponse(status_code=422, content={'detail': [{'loc': list(item['loc']), 'msg': item['msg'], 'type': item['type']} for item in error.errors()]})


@app.exception_handler(SQLAlchemyError)
def database_error(request, error):
    return JSONResponse(status_code=503, content={'detail': '잠시 후 다시 시도해 주세요.'})


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="oneul-menu")


@app.get('/api/ready', response_model=HealthResponse)
def ready(engine=Depends(get_engine)) -> HealthResponse:
    try:
        with engine.connect() as connection:
            schema = connection.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'app'")).scalar_one_or_none()
            if schema is None:
                raise HTTPException(status_code=503, detail='서비스 준비 중입니다.')
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail='서비스 준비 중입니다.') from None
    return HealthResponse(status='ok', service='oneul-menu')
