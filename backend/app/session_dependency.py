from fastapi import Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine


def get_session(engine=Depends(get_engine)):
    try:
        with Session(engine) as session:
            yield session
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail='자료를 불러오거나 저장하지 못했어요. 잠시 후 다시 시도해 주세요.') from None
