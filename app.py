"""Private Cloud Run entry point for Cyrus contest-intake staging."""

from __future__ import annotations

from datetime import date, datetime, timezone
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, request

from cyrus_intake.discovery import discover_urls, fetch_sources
from cyrus_intake.parser import IntakeError, build_bundle
from cyrus_intake.schedule import scheduled_week
from cyrus_intake.storage import store_stage


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "cyrus-contest-intake", "mode": "STAGING_ONLY"})


@app.route("/run", methods=["GET", "POST"])
def run_stage():
    try:
        season = _integer("season")
        week = _integer("week")
        write = request.args.get("write", "false").lower() == "true"
        if request.args.get("write", "false").lower() not in {"true", "false"}:
            raise IntakeError("write must be true or false")
        return jsonify(_stage(season, week, write))
    except IntakeError as exc:
        app.logger.warning("intake refused route=/run reason=%s", str(exc))
        return jsonify({"ok": False, "error": str(exc), "status": "REFUSED_NO_WRITE"}), 422
    except Exception as exc:
        app.logger.exception("unexpected intake failure")
        return jsonify({"ok": False, "error": f"unexpected {type(exc).__name__}", "status": "REFUSED_NO_WRITE"}), 500


@app.post("/scheduled")
def run_scheduled_stage():
    """Stage the current configured NFL week for the private weekly scheduler."""
    try:
        season = _env_integer("SCHEDULE_SEASON")
        week_one = _env_date("SCHEDULE_WEEK1_DATE")
        timezone_name = os.environ.get("SCHEDULE_TIMEZONE", "America/Chicago").strip()
        try:
            local_date = datetime.now(ZoneInfo(timezone_name)).date()
        except ZoneInfoNotFoundError as exc:
            raise IntakeError("SCHEDULE_TIMEZONE is invalid") from exc

        week = scheduled_week(local_date, week_one)
        if week is None:
            return jsonify(
                {
                    "ok": True,
                    "status": "SKIPPED_OUTSIDE_SUPPORTED_WEEKS",
                    "writeRequested": False,
                    "season": season,
                    "localDate": local_date.isoformat(),
                }
            )
        return jsonify(_stage(season, week, True))
    except IntakeError as exc:
        app.logger.warning("intake refused route=/scheduled reason=%s", str(exc))
        return jsonify({"ok": False, "error": str(exc), "status": "REFUSED_NO_WRITE"}), 422
    except Exception as exc:
        app.logger.exception("unexpected scheduled intake failure")
        return jsonify({"ok": False, "error": f"unexpected {type(exc).__name__}", "status": "REFUSED_NO_WRITE"}), 500


def _stage(season: int, week: int, write: bool) -> dict[str, object]:
    urls = discover_urls(season, week)
    raw = fetch_sources(urls)
    bundle = build_bundle(
        season=season,
        week=week,
        urls=urls,
        generated_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **raw,
    )
    result: dict[str, object] = {"ok": True, "writeRequested": write, "bundle": bundle}
    if write:
        bucket = os.environ.get("STAGING_BUCKET", "").strip()
        if not bucket:
            raise IntakeError("STAGING_BUCKET is not configured")
        result["storage"] = store_stage(bucket, bundle, raw)
    return result


def _integer(name: str) -> int:
    raw = request.args.get(name, "")
    if not raw.isdigit():
        raise IntakeError(f"{name} must be an integer")
    return int(raw)


def _env_integer(name: str) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw.isdigit():
        raise IntakeError(f"{name} must be an integer")
    return int(raw)


def _env_date(name: str) -> date:
    raw = os.environ.get(name, "").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise IntakeError(f"{name} must be an ISO date") from exc
