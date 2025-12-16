import os
import sqlite3
from flask import Flask, request, jsonify, send_file, abort

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(APP_DIR, "database.db"))

app = Flask(__name__)

# --- Senha (admin) ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")


def check_password(req) -> bool:
    sent = req.headers.get("X-Admin-Password")
    return bool(ADMIN_PASSWORD) and sent == ADMIN_PASSWORD


# --- CORS (para GitHub Pages chamar a API do Render) ---
GITHUB_PAGES_ORIGIN = "https://somauma.github.io"


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin == GITHUB_PAGES_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Password"
    return response


@app.route("/api/<path:_>", methods=["OPTIONS"])
def cors_preflight(_):
    return ("", 204)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        create table if not exists procedimentos (
          id integer primary key autoincrement,
          departamento text not null,
          codigo text not null,
          data_publicacao text not null, -- YYYY-MM-DD
          titulo text not null,
          resumo text not null,
          link text not null,
          created_at text not null default (datetime('now'))
        );
        """
    )
    conn.execute("create index if not exists idx_proc_depto on procedimentos (departamento);")
    conn.execute("create index if not exists idx_proc_data on procedimentos (data_publicacao desc);")
    conn.commit()
    conn.close()


@app.route("/", methods=["GET"])
def home():
    index_path = os.path.join(APP_DIR, "index.html")
    if not os.path.exists(index_path):
        abort(404)
    return send_file(index_path)


@app.route("/api/procedimentos", methods=["GET"])
def listar_procedimentos():
    departamento = request.args.get("departamento")

    conn = get_db()
    if departamento:
        rows = conn.execute(
            """
            select id, departamento, codigo, data_publicacao, titulo, resumo, link
            from procedimentos
            where departamento = ?
            order by data_publicacao desc, id desc
            """,
            (departamento,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            select id, departamento, codigo, data_publicacao, titulo, resumo, link
            from procedimentos
            order by data_publicacao desc, id desc
            """
        ).fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])


@app.route("/api/procedimentos", methods=["POST"])
def criar_procedimento():
    if not check_password(request):
        return jsonify({"error": "Senha inválida."}), 401

    data = request.get_json(silent=True) or {}

    departamento = (data.get("departamento") or "").strip()
    codigo = (data.get("codigo") or "").strip()
    data_publicacao = (data.get("data_publicacao") or "").strip()
    titulo = (data.get("titulo") or "").strip()
    resumo = (data.get("resumo") or "").strip()
    link = (data.get("link") or "").strip()

    obrigatorios = [departamento, codigo, data_publicacao, titulo, resumo, link]
    if any(not x for x in obrigatorios):
        return jsonify({"error": "Campos obrigatórios faltando."}), 400

    deptos_validos = {"FIN", "RHU", "JUR", "INC", "COM", "MKT", "ENG", "SAC"}
    if departamento not in deptos_validos:
        return jsonify({"error": "Departamento inválido."}), 400

    if len(data_publicacao) != 10 or data_publicacao[4] != "-" or data_publicacao[7] != "-":
        return jsonify({"error": "Data inválida (use YYYY-MM-DD)."}), 400

    conn = get_db()
    cur = conn.execute(
        """
        insert into procedimentos (departamento, codigo, data_publicacao, titulo, resumo, link)
        values (?, ?, ?, ?, ?, ?)
        """,
        (departamento, codigo, data_publicacao, titulo, resumo, link),
    )
    new_id = cur.lastrowid
    conn.commit()

    row = conn.execute(
        """
        select id, departamento, codigo, data_publicacao, titulo, resumo, link
        from procedimentos
        where id = ?
        """,
        (new_id,),
    ).fetchone()
    conn.close()

    return jsonify(dict(row)), 201


@app.route("/api/procedimentos/<int:proc_id>", methods=["DELETE"])
def deletar_procedimento(proc_id: int):
    if not check_password(request):
        return jsonify({"error": "Senha inválida."}), 401

    conn = get_db()
    cur = conn.execute("delete from procedimentos where id = ?", (proc_id,))
    conn.commit()
    conn.close()

    if cur.rowcount == 0:
        return jsonify({"error": "Procedimento não encontrado."}), 404

    return ("", 204)


# init DB tanto local quanto no gunicorn (Render)
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
