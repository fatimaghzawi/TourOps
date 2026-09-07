from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConfigurationError, ConnectionFailure, PyMongoError, ServerSelectionTimeoutError

from core.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_CONNECT_TIMEOUT_MS = 8000


def _connect(uri: str) -> MongoClient:
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=_CONNECT_TIMEOUT_MS,
        connectTimeoutMS=_CONNECT_TIMEOUT_MS,
    )


def _windows_srv_hosts(hostname: str) -> list[tuple[str, int]]:
    """Resolve MongoDB SRV records via the Windows DNS API (not dnspython)."""
    record = f"_mongodb._tcp.{hostname}"
    command = (
        f"Resolve-DnsName -Name '{record}' -Type SRV | "
        "Select-Object NameTarget, Port | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    hosts: list[tuple[str, int]] = []
    for row in payload:
        target = str(row.get("NameTarget") or "").rstrip(".")
        try:
            port = int(row.get("Port") or 27017)
        except (TypeError, ValueError):
            port = 27017
        if target:
            hosts.append((target, port))
    return hosts


def _standard_uri_from_srv(uri: str) -> Optional[str]:
    """Rewrite mongodb+srv:// to mongodb:// using OS DNS when dnspython fails."""
    if not uri.startswith("mongodb+srv://"):
        return None
    parsed = urlsplit(uri)
    hostname = parsed.hostname
    if not hostname:
        return None
    hosts = _windows_srv_hosts(hostname) if os.name == "nt" else []
    if not hosts:
        return None
    netloc = ",".join(f"{host}:{port}" for host, port in hosts)
    if parsed.username is not None:
        userinfo = quote(parsed.username, safe="")
        if parsed.password is not None:
            userinfo += ":" + quote(parsed.password, safe="")
        netloc = f"{userinfo}@{netloc}"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("tls", "true")
    query.setdefault("authSource", "admin")
    return urlunsplit(("mongodb", netloc, parsed.path, urlencode(query), parsed.fragment))


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = settings.MONGODB_URI
        try:
            _client = _connect(uri)
        except ConfigurationError as exc:
            fallback = _standard_uri_from_srv(uri)
            if fallback is None:
                logger.exception("Could not create MongoClient")
                raise DatabaseUnavailableError("Could not connect to MongoDB.") from exc
            logger.warning("mongodb+srv DNS lookup failed; retrying with a standard mongodb:// URI")
            try:
                _client = _connect(fallback)
            except PyMongoError as retry_exc:
                logger.exception("Could not create MongoClient")
                raise DatabaseUnavailableError("Could not connect to MongoDB.") from retry_exc
        except PyMongoError as exc:
            logger.exception("Could not create MongoClient")
            raise DatabaseUnavailableError("Could not connect to MongoDB.") from exc
    return _client


def get_database() -> Database:
    return get_client()[settings.MONGODB_DB_NAME]


def get_collection(name: str) -> Collection:
    return get_database()[name]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError, PyMongoError):
        logger.warning("MongoDB ping failed", exc_info=True)
        return False


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
