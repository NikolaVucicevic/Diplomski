from sqlalchemy import Column, Integer, String
from .database import Base


class Saga(Base):
    __tablename__ = "sagas"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=True)

    status = Column(
        String,
        nullable=False,
        default="STARTED"
    )

    current_step = Column(
        String,
        nullable=False,
        default="STARTED"
    )