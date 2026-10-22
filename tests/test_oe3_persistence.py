"""PostgreSQL persistente entre procesos: prueba con BD temporal de CI, sin datos reales."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

URL=os.environ.get("OE3_POSTGRES_TEST_URL")
@pytest.mark.skipif(not URL,reason="Requiere PostgreSQL CI")
def test_persist_between_processes(tmp_path):
    engine=create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS oe3_persist_test"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS oe3_persist_test.prueba (id INT PRIMARY KEY, dato TEXT)"))
        conn.execute(text("DELETE FROM oe3_persist_test.prueba"))
        conn.execute(text("INSERT INTO oe3_persist_test.prueba (id,dato) VALUES (1,'dato-sintetico')"))
    engine.dispose()
    # Abrir nueva conexión en un PROCESO de Python independiente, no reutilizar la sesión original.
    script=tmp_path/"lectura.py"
    script.write_text("""from sqlalchemy import create_engine, text
import os
engine=create_engine(os.environ['OE3_POSTGRES_TEST_URL'])
with engine.connect() as conn:
    assert conn.scalar(text("SELECT dato FROM oe3_persist_test.prueba WHERE id=1"))=='dato-sintetico'
engine.dispose()
print('persistencia_entre_procesos=OK')
""")
    try:
        out=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,env=os.environ,
                           timeout=25,check=True)
        assert "persistencia_entre_procesos=OK" in out.stdout
    finally:
        with create_engine(URL).begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS oe3_persist_test CASCADE"))
