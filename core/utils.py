from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math


def dataclass_to_dict(value: object) -> object:
    if is_dataclass(value):
        return dataclass_to_dict(asdict(value))
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, tuple):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        if math.isnan(value):
            return "N/A"
        if math.isinf(value):
            return "inf"
    return f"{value:,.{digits}f}"


def format_ratio(value: float | None, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{digits}f}"


def format_percent(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{digits}f}%"


def compact_status(status: str) -> str:
    normalized = status.strip().upper()
    if normalized in {"PASS", "OK"}:
        return "PASS"
    if normalized in {"FAIL", "NOT OK"} or "NOT OK" in normalized:
        return "FAIL"
    if "REVIEW" in normalized or "WARNING" in normalized:
        return "REVIEW"
    return status


def percent_difference(reference: float | None, candidate: float | None) -> float | None:
    if reference is None or candidate is None:
        return None
    if reference == 0:
        return 0.0 if candidate == 0 else None
    return abs(reference - candidate) / abs(reference) * 100


def longitudinal_bar_mark(fy_ksc: float) -> str:
    return "RB" if round(fy_ksc) == 2400 else "DB"


def stirrup_bar_mark(fvy_ksc: float) -> str:
    return "RB" if round(fvy_ksc) == 2400 else "DB"
