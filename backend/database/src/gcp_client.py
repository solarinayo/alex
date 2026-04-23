"""
Cloud SQL (PostgreSQL) client with the same public API as DataAPIClient, for GCP / Cloud Run.

Set INSTANCE_CONNECTION_NAME, DB_USER, DB_NAME, and DB_PASSWORD (injected on Cloud Run from
Secret Manager). The Cloud Run service should mount the Cloud SQL Unix socket at /cloudsql/...
see terraform/gcp/cloud_run.tf.
"""

import json
import logging
import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import date, datetime

import psycopg2
from psycopg2.extras import RealDictCursor

# Load .env for local use
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _is_gcp_sql_configured() -> bool:
    """
    True when we can open Postgres for GCP: DB_USER, DB_NAME, DB_PASSWORD, plus either
    - DB_HOST (+ optional DB_PORT): local dev via Cloud SQL Auth Proxy (TCP), or
    - INSTANCE_CONNECTION_NAME: Cloud Run socket /cloudsql/PROJ:REGION:INSTANCE
    """
    if not (
        os.environ.get("DB_USER")
        and os.environ.get("DB_NAME")
        and "DB_PASSWORD" in os.environ
    ):
        return False
    if (os.environ.get("DB_HOST") or "").strip():
        return True
    return bool(os.environ.get("INSTANCE_CONNECTION_NAME"))


def get_gcp_postgres_connection():
    """Get a psycopg2 connection for Cloud SQL (proxy TCP or Cloud Run socket)."""
    if not _is_gcp_sql_configured():
        raise ValueError(
            "GCP DB: set DB_USER, DB_NAME, DB_PASSWORD and either "
            "DB_HOST (local proxy) or INSTANCE_CONNECTION_NAME (Cloud Run / socket)."
        )
    return _get_connection()


def _sql_data_api_to_psycopg(sql: str) -> str:
    """
    Map Aurora Data API style :name and :name::type placeholders to psycopg2 %(name)s form.
    """

    def repl(m: re.Match) -> str:
        return f"%({m.group(1)})s{m.group(2) or ''}"

    return re.sub(
        r":([a-zA-Z_][a-zA-Z0-9_]*)(::[a-zA-Z0-9\._\(\)\[\] ]+)?",
        repl,
        sql,
    )


def _data_api_param_value_to_py(field: Dict[str, Any]) -> Any:
    v = field.get("value", field)
    if isinstance(v, dict) and "isNull" in v and v.get("isNull"):
        return None
    if not isinstance(v, dict):
        return v
    if "booleanValue" in v:
        return v["booleanValue"]
    if "longValue" in v:
        return v["longValue"]
    if "doubleValue" in v:
        return v["doubleValue"]
    if "stringValue" in v:
        s = v["stringValue"]
        if s and s[0] in "{[":
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                pass
        return s
    if "isNull" in v and v["isNull"]:
        return None
    return None


def _data_api_params_to_dict(parameters: Optional[List[Dict]]) -> Optional[Dict[str, Any]]:
    if not parameters:
        return None
    out: Dict[str, Any] = {}
    for p in parameters:
        if "name" in p and "value" in p:
            out[p["name"]] = _data_api_param_value_to_py(p)
        elif "name" in p:
            out[p["name"]] = _data_api_param_value_to_py(p)
    return out


def _get_connection():
    if not _is_gcp_sql_configured():
        raise ValueError(
            "GCP Cloud SQL: set DB_USER, DB_NAME, DB_PASSWORD, and "
            "DB_HOST+DB_PORT for local proxy, or INSTANCE_CONNECTION_NAME for /cloudsql socket."
        )
    # Local: Cloud SQL Auth Proxy listens on 127.0.0.1:5432 (or DB_PORT) — /cloudsql does not exist on macOS
    host = (os.environ.get("DB_HOST") or "").strip()
    if host:
        port = int(os.environ.get("DB_PORT", "5432"))
        return psycopg2.connect(
            host=host,
            port=port,
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            dbname=os.environ["DB_NAME"],
            sslmode="disable",
        )
    inst = os.environ["INSTANCE_CONNECTION_NAME"]
    return psycopg2.connect(
        host=f"/cloudsql/{inst}",
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ["DB_NAME"],
    )


def _row_value_to_data_api_field(value: Any) -> Dict:
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, Decimal):
        return {"stringValue": str(value)}
    if isinstance(value, (date, datetime)):
        return {"stringValue": value.isoformat()}
    if isinstance(value, (dict, list)):
        return {"stringValue": json.dumps(value)}
    return {"stringValue": str(value)}


class CloudSQLClient:
    """
    Psycopg2-backed client matching DataAPIClient’s query/insert/update/delete contract.
    """

    def __init__(self) -> None:
        if not _is_gcp_sql_configured():
            raise ValueError(
                "Cloud SQL: set DB_USER, DB_NAME, DB_PASSWORD and either "
                "DB_HOST (proxy) or INSTANCE_CONNECTION_NAME (socket on Cloud Run)."
            )
        self.database = os.environ.get("DB_NAME", "alex")

    def execute(self, sql: str, parameters: List[Dict] = None) -> Dict:
        csql = _sql_data_api_to_psycopg(sql)
        params = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(csql, params or None)
                if cur.description is not None:
                    raw_rows = cur.fetchall()
                    return {
                        "columnMetadata": [{"name": d[0]} for d in cur.description],
                        "records": [
                            [_row_value_to_data_api_field(c) for c in row] for row in raw_rows
                        ],
                        "numberOfRecordsUpdated": cur.rowcount or len(raw_rows),
                    }
                return {"numberOfRecordsUpdated": cur.rowcount or 0}

    def query(self, sql: str, parameters: List[Dict] = None) -> List[Dict]:
        csql = _sql_data_api_to_psycopg(sql)
        params = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(csql, params or None)
                return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, parameters: List[Dict] = None) -> Optional[Dict]:
        csql = _sql_data_api_to_psycopg(sql)
        params = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(csql, params or None)
                r = cur.fetchone()
                return dict(r) if r else None

    def _build_parameters(self, data: Dict) -> List[Dict]:
        """Match DataAPIClient’s wire format (shared contract with models)."""
        if not data:
            return []
        parameters = []
        for key, value in data.items():
            param = {"name": key}
            if value is None:
                param["value"] = {"isNull": True}
            elif isinstance(value, bool):
                param["value"] = {"booleanValue": value}
            elif isinstance(value, int):
                param["value"] = {"longValue": value}
            elif isinstance(value, float):
                param["value"] = {"doubleValue": value}
            elif isinstance(value, Decimal):
                param["value"] = {"stringValue": str(value)}
            elif isinstance(value, (date, datetime)):
                param["value"] = {"stringValue": value.isoformat()}
            elif isinstance(value, (dict, list)):
                param["value"] = {"stringValue": json.dumps(value)}
            else:
                param["value"] = {"stringValue": str(value)}
            parameters.append(param)
        return parameters

    def _extract_value(self, field: Dict) -> Any:
        if field.get("isNull"):
            return None
        if "booleanValue" in field:
            return field["booleanValue"]
        if "longValue" in field:
            return field["longValue"]
        if "doubleValue" in field:
            return field["doubleValue"]
        if "stringValue" in field:
            s = field["stringValue"]
            if s and s[0] in "[{":
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
            return s
        return None

    def insert(self, table: str, data: Dict, returning: str = None) -> str:
        columns = list(data.keys())
        placeholders = []
        for col in columns:
            v = data[col]
            if isinstance(v, (dict, list)):
                placeholders.append(f":{col}::jsonb")
            elif isinstance(v, Decimal):
                placeholders.append(f":{col}::numeric")
            elif isinstance(v, date) and not isinstance(v, datetime):
                placeholders.append(f":{col}::date")
            elif isinstance(v, datetime):
                placeholders.append(f":{col}::timestamp")
            else:
                placeholders.append(f":{col}")
        sql = f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({", ".join(placeholders)})'
        if returning:
            sql += f" RETURNING {returning}"
        parameters = self._build_parameters(data)
        csql = _sql_data_api_to_psycopg(sql)
        params = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(csql, params or None)
                if returning:
                    r = cur.fetchone()
                    if r:
                        return str(r[0]) if r[0] is not None else None
        return None

    def update(self, table: str, data: Dict, where: str, where_params: Dict = None) -> int:
        set_parts = []
        for col, val in data.items():
            if isinstance(val, (dict, list)):
                set_parts.append(f"{col} = :{col}::jsonb")
            elif isinstance(val, Decimal):
                set_parts.append(f"{col} = :{col}::numeric")
            elif isinstance(val, date) and not isinstance(val, datetime):
                set_parts.append(f"{col} = :{col}::date")
            elif isinstance(val, datetime):
                set_parts.append(f"{col} = :{col}::timestamp")
            else:
                set_parts.append(f"{col} = :{col}")
        sql = f'UPDATE {table} SET {", ".join(set_parts)} WHERE {where}'
        all_params = {**data, **(where_params or {})}
        parameters = self._build_parameters(all_params)
        csql = _sql_data_api_to_psycopg(sql)
        pdict = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(csql, pdict or None)
                return cur.rowcount

    def delete(self, table: str, where: str, where_params: Dict = None) -> int:
        sql = f"DELETE FROM {table} WHERE {where}"
        parameters = self._build_parameters(where_params) if where_params else None
        csql = _sql_data_api_to_psycopg(sql)
        pdict = _data_api_params_to_dict(parameters)
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(csql, pdict or None)
                return cur.rowcount

    def begin_transaction(self) -> str:
        raise NotImplementedError("Cloud SQL client: use per-request autocommit (Aurora path supports Data API tx).")

    def commit_transaction(self, transaction_id: str) -> None:
        raise NotImplementedError("Cloud SQL client: transactions not exposed.")

    def rollback_transaction(self, transaction_id: str) -> None:
        raise NotImplementedError("Cloud SQL client: transactions not exposed.")
