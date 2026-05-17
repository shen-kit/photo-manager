from __future__ import annotations

from enum import StrEnum


class NotificationLevel(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationCategory(StrEnum):
    SCAN = "scan"
    ASSET = "asset"
    WORKER = "worker"
    FACE = "face"
    SEARCH = "search"
    SYSTEM = "system"
