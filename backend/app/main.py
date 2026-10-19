from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_engine
from app.food_api import router as food_router


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(title="오늘 뭐 먹지?", version="0.1.0")
app.include_router(food_router)


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
