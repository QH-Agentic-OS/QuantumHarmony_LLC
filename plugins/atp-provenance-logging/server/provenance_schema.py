"""Explicit SQLite readiness and transactional, evidence-preserving upgrades.

No connection/read path migrates. Version 2 adds harness step-capture tables
(see STEP_CAPTURE.md); version 1 is the complete owned API schema; version 0
is the historical unversioned schema, not authenticated data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

SCHEMA_VERSION = 2
# Tables introduced by version 2. A physically complete version-1 ledger lacks
# exactly these, and is a supported upgrade source rather than a conflict.
V2_TABLES = (
    'trajectory_chunks', 'agent_steps', 'step_tool_calls', 'step_artifacts', 'capture_policies',
)
OPTIONAL_TABLES = ('manifest_bindings', 'provenance_operations', *V2_TABLES)
ADDITIONS = (
    ('manifest_layers', 'manifest_binding_id', 'TEXT'),
    ('action_refs', 'manifest_binding_id', 'TEXT'),
    ('action_refs', 'sequence_no', 'INTEGER'),
    ('agent_logs', 'canonical_body_json', 'TEXT'),
    ('agent_logs', 'owner_json', 'TEXT'),
    ('agent_logs', 'receipt_json', 'TEXT'),
    ('manifest_bindings', 'owner_json', 'TEXT'),
    ('manifest_bindings', 'parent_prov_id', 'TEXT'),
    ('manifest_bindings', 'canonical_body_json', 'TEXT'),
    ('manifest_bindings', 'receipt_json', 'TEXT'),
)
INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_manifest_layer_binding ON manifest_layers(manifest_binding_id,layer_name,bound_at);
CREATE INDEX IF NOT EXISTS idx_action_binding ON action_refs(manifest_binding_id);
CREATE INDEX IF NOT EXISTS idx_binding_session ON manifest_bindings(session_id);
'''


class SchemaError(sqlite3.DatabaseError):
    """A safe diagnostic containing schema names, never ledger contents."""


@contextmanager
def _connection(*args, **kwargs):
    conn = sqlite3.connect(*args, **kwargs)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _execute_schema(conn, script):
    # executescript commits an existing transaction; execute DDL individually.
    for statement in script.split(';'):
        if statement.strip():
            conn.execute(statement)


def _tables(conn):
    return {row[0]: {r[1]: tuple(r[2:]) for r in conn.execute('PRAGMA table_info("' + row[0].replace('"', '""') + '")')}
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


@lru_cache(maxsize=4)
def _expected(schema):
    with _connection(':memory:') as conn:
        _execute_schema(conn, schema)
        base = _tables(conn)
        for table, column, kind in ADDITIONS:
            if column not in base[table]:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
        return base, _tables(conn)


def inspect_schema(conn, schema, *, allow_empty=False):
    _base, expected = _expected(schema)
    actual = _tables(conn)
    version = conn.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 1, SCHEMA_VERSION):
        raise SchemaError('unsupported schema version')
    if not actual:
        if allow_empty and version == 0:
            return {'version': 0, 'ready': False, 'missing': ['empty ledger']}
        raise SchemaError('empty ledger; explicit initialization required')
    if 'agent_logs' not in actual:
        raise SchemaError('unsupported ledger layout: agent_logs missing')
    if set(actual) - set(expected):
        raise SchemaError('unsupported ledger tables; review historical layout')
    optional = {(t, c) for t, c, _ in ADDITIONS}
    missing = []
    for table, cols in expected.items():
        if table not in actual:
            if table not in OPTIONAL_TABLES:
                raise SchemaError(f'unsupported ledger layout: {table} missing')
            missing.append(table)
            continue
        if set(actual[table]) - set(cols):
            raise SchemaError(f'unsupported columns in {table}')
        for column, definition in cols.items():
            if column not in actual[table]:
                if (table, column) not in optional:
                    raise SchemaError(f'unsupported ledger layout: {table}.{column} missing')
                missing.append(f'{table}.{column}')
            elif actual[table][column] != definition:
                raise SchemaError(f'conflicting column definition: {table}.{column}')
    # Version markers cannot legitimize incomplete physical schemas.
    if version == SCHEMA_VERSION and missing:
        raise SchemaError('schema version conflicts with physical layout')
    if version == 1 and any(item not in V2_TABLES for item in missing):
        raise SchemaError('schema version conflicts with physical layout')
    return {'version': version, 'ready': version == SCHEMA_VERSION and not missing,
            'missing': missing, 'migration_required': version < SCHEMA_VERSION}


def require_ready(conn, schema):
    report = inspect_schema(conn, schema)
    if not report['ready']:
        raise SchemaError('schema upgrade required; run provenance_schema.py check --db <absolute-path>, then dry-run')
    return report


def _evidence(conn, tables):
    """Digest every original cell in PK order, including opaque stored evidence."""
    result = {}
    for table, columns in tables.items():
        names = list(columns)
        ordering = [n for n, definition in columns.items() if definition[-1]] or names
        quoted = lambda values: ','.join('"' + v.replace('"', '""') + '"' for v in values)
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute(f'SELECT {quoted(names)} FROM "{table}" ORDER BY {quoted(ordering)}'):
            for value in row:
                data = repr(value).encode('utf-8')
                digest.update(len(data).to_bytes(8, 'big')); digest.update(data)
            count += 1
        result[table] = (count, digest.hexdigest())
    return result


def upgrade_connection(conn, schema, *, allow_empty=False):
    """Caller holds transaction/backup; no guesses about ownership or bindings."""
    report = inspect_schema(conn, schema, allow_empty=allow_empty)
    if report['ready']:
        return report
    tables = _tables(conn)
    before = _evidence(conn, tables)
    _execute_schema(conn, schema)
    for table, column, kind in ADDITIONS:
        if column not in _tables(conn)[table]:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
    _execute_schema(conn, INDEXES)
    if before != _evidence(conn, tables):
        raise SchemaError('migration changed historical evidence')
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SchemaError('ledger integrity check failed')
    conn.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
    return require_ready(conn, schema)


def _path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise SchemaError('an explicit absolute ledger/backup path is required')
    return path.resolve()


def _existing(path):
    if not path.is_file():
        raise SchemaError('selected ledger is missing or not a file; no database was created')


def check(path, schema):
    path = _path(path)
    _existing(path)
    with _connection(path.as_uri() + '?mode=ro', uri=True) as conn:
        report = inspect_schema(conn, schema)
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SchemaError('ledger integrity check failed')
        return {'database': str(path), **report}


def upgrade(path, backup, schema):
    path, backup = _path(path), _path(backup)
    _existing(path)
    if path == backup:
        raise SchemaError('backup must differ from ledger')
    conn = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        conn.execute('BEGIN IMMEDIATE')
        report = inspect_schema(conn, schema)
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SchemaError('ledger integrity check failed')
        if report['ready']:
            conn.rollback()
            return {'database': str(path), **report, 'changed': False}
        # Never overwrite an earlier backup. Writer lock spans backup + upgrade.
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with _connection(path.as_uri() + '?mode=ro', uri=True) as source, _connection(backup) as dest:
                source.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise SchemaError('backup integrity check failed')
            # Validate original cell equality before authorizing any mutation.
            with _connection(backup.as_uri() + '?mode=ro', uri=True) as saved:
                if _evidence(conn, _tables(conn)) != _evidence(saved, _tables(conn)):
                    raise SchemaError('backup evidence mismatch')
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
        report = upgrade_connection(conn, schema)
        conn.commit()
        return {'database': str(path), 'backup': str(backup), **report, 'changed': True}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    from provenance_core import SCHEMA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'dry-run', 'upgrade'])
    parser.add_argument('--db', required=True, help='explicit absolute selected ledger path; .env.local is not loaded')
    parser.add_argument('--backup', help='new absolute backup path, required for upgrade')
    args = parser.parse_args()
    try:
        if args.command == 'check':
            report = check(args.db, SCHEMA)
        elif args.command == 'upgrade':
            if not args.backup:
                parser.error('upgrade requires --backup')
            report = upgrade(args.db, args.backup, SCHEMA)
        else:
            original = check(args.db, SCHEMA)
            with tempfile.TemporaryDirectory(prefix='prove-schema-dry-run-') as directory:
                copy = Path(directory) / 'ledger.db'
                with _connection(_path(args.db).as_uri() + '?mode=ro', uri=True) as source, _connection(copy) as dest:
                    source.backup(dest)
                report = upgrade(str(copy), str(Path(directory) / 'before.db'), SCHEMA)
                report = {**report, 'database': original['database'], 'dry_run': True}
                report.pop('backup', None)
        print(json.dumps(report, sort_keys=True))
        return 0 if report['ready'] else 2
    except (sqlite3.Error, OSError) as error:
        # sqlite error messages can include stored constraint values; emit safe class.
        message = str(error) if isinstance(error, SchemaError) else type(error).__name__
        print(json.dumps({'ready': False, 'error': message, 'database': str(Path(args.db).expanduser().absolute())}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
