from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StaffDepartmentOrder(Base):
    __tablename__ = "staff_department_orders"

    department: Mapped[str] = mapped_column(Text, primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
