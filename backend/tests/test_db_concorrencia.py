"""Primeiro acesso depois de uma atualização: várias requisições simultâneas encontram migrações pendentes.

Visto com o painel: a página inicial deu erro 500 na primeira visita, porque duas rotas aplicavam a mesma migração.
"""
from __future__ import annotations

import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

from app.db import MIGRATIONS_DIR, _statements, connect, migrate
from app.studio import store

THREADS = 6


def race(path: Path, action) -> list[str]:
    errors: list[str] = []
    barrier = threading.Barrier(THREADS)

    def run():
        conn = None
        try:
            # A barreira vem antes de tudo: uma falha ao abrir o banco não pode deixar as outras esperando.
            barrier.wait(timeout=20)
            conn = connect(path)
            action(conn)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{type(error).__name__}: {error}")
        finally:
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=run, daemon=True) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "travou"
    return errors


@pytest.mark.parametrize("folder", [MIGRATIONS_DIR, store.MIGRATIONS], ids=["pesquisa", "estudio"])
def test_simultaneous_migration_of_a_new_database(tmp_path, folder):
    path = tmp_path / "novo.sqlite"
    assert race(path, lambda conn: migrate(conn, folder)) == []
    conn = connect(path)
    names = [row["name"] for row in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]
    assert names == sorted(script.name for script in folder.glob("*.sql"))
    conn.close()


def test_simultaneous_update_keeps_existing_rows(tmp_path):
    """Banco na versão anterior, com dados: é o caso de quem atualiza o aplicativo."""
    old = tmp_path / "antigas"
    old.mkdir()
    for script in sorted(MIGRATIONS_DIR.glob("*.sql"))[:3]:
        shutil.copy(script, old)
    path = tmp_path / "antigo.sqlite"
    conn = connect(path)
    migrate(conn, old)
    conn.execute("INSERT INTO research_runs (id, kind, query, data_origin, executed_at) VALUES ('run_a', 'videos', 'roma', 'demo', '2026-11-01T00:00:00Z')")
    conn.commit()
    conn.close()
    assert race(path, migrate) == []
    conn = connect(path)
    assert conn.execute("SELECT query, provenance_json FROM research_runs").fetchone()["query"] == "roma"
    assert conn.execute("SELECT COUNT(*) AS n FROM schema_migrations WHERE name = '004_api_real.sql'").fetchone()["n"] == 1
    conn.close()


def test_failed_migration_leaves_nothing_behind(tmp_path):
    folder = tmp_path / "ruim"
    folder.mkdir()
    (folder / "001_ruim.sql").write_text("CREATE TABLE boa (id INTEGER);\nCREATE TABLE boa (id INTEGER);\n", encoding="utf-8")
    conn = connect(tmp_path / "x.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, folder)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'boa'").fetchone() is None
    assert conn.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"] == 0
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_statement_split_ignores_semicolons_in_comments_and_text():
    script = "-- comentário; com ponto e vírgula\nCREATE TABLE a (b TEXT DEFAULT 'x;y');\nINSERT INTO a VALUES ('z;w');\n"
    statements = [item.strip() for item in _statements(script)]
    assert len(statements) == 2 and "x;y" in statements[0] and "z;w" in statements[1]


def test_every_real_migration_splits_into_complete_statements(tmp_path):
    """Nenhum comando pode ser perdido na divisão: cada arquivo termina sem sobra."""
    for folder in (MIGRATIONS_DIR, store.MIGRATIONS):
        for script in folder.glob("*.sql"):
            text = script.read_text(encoding="utf-8")
            assert list(_statements(text)), script.name
            assert text.count("CREATE TABLE") == sum(item.count("CREATE TABLE") for item in _statements(text)), script.name
