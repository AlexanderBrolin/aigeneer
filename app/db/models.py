from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_user: Mapped[str] = mapped_column(String(128), default="deploy")
    ssh_key_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ssh_password: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    checks: Mapped[list["ServerCheck"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    check_runs: Mapped[list["CheckRun"]] = relationship(back_populates="server")


class ServerCheck(Base):
    __tablename__ = "server_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    server: Mapped["Server"] = relationship(back_populates="checks")

    __table_args__ = (Index("idx_server_check", "server_id", "check_name", unique=True),)


class CheckRun(Base):
    __tablename__ = "check_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, ForeignKey("servers.id"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    check_name: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("running", "ok", "incident", "error", name="check_run_status"), default="running"
    )
    signal_count: Mapped[int] = mapped_column(Integer, default=0)

    server: Mapped["Server"] = relationship(back_populates="check_runs")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="check_run")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("check_runs.id"), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(
        Enum("critical", "warning", "info", name="incident_severity"), nullable=False
    )
    problem_type: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("new", "notified", "actioned", "ignored", "resolved", name="incident_status"), default="new"
    )
    action_taken: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    check_run: Mapped["CheckRun | None"] = relationship(back_populates="incidents")

    __table_args__ = (
        Index("idx_host_status", "host", "status"),
        Index("idx_thread", "thread_id"),
    )
