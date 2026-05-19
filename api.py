"""
DRG Dashboard — API Flask
==========================
Un seul endpoint : POST /api/parse
  - Reçoit un fichier .sav (multipart/form-data)
  - Reçoit le pseudo du joueur (form field "player_name")
  - Retourne le JSON du dashboard

Analogie : c'est un guichet. Le joueur dépose son fichier save sur le comptoir,
et le guichet lui remet une fiche résumé lisible. Rien n'est conservé.

Usage local :
    pip install flask
    python api.py
    → http://localhost:5000
"""

import io
import json
import tempfile
import os

from flask import Flask, request, jsonify
from flask_cors import CORS

from parse_save import parse_gvas
from stats_builder import build_dashboard_data

# ── App Flask ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

# CORS : autorise le frontend React (localhost:5173 en dev, Vercel en prod)
# En production, remplacer "*" par l'URL exacte du frontend Vercel
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Limites ───────────────────────────────────────────────────────────────────

MAX_FILE_SIZE_MB = 5
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024


# ── Endpoint principal ────────────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def parse_save_file():
    """
    Reçoit un fichier .sav et un pseudo, retourne les stats du dashboard.

    Form data :
        file        : le fichier .sav (required)
        player_name : le pseudo du joueur (required)

    Réponse 200 :
        { "ok": true, "data": { ... } }

    Réponse 4xx/5xx :
        { "ok": false, "error": "message d'erreur lisible" }
    """

    # 1. Vérifier la présence du fichier
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    if not file.filename.endswith(".sav"):
        return jsonify({"ok": False, "error": "File must be a .sav file"}), 400

    # 2. Vérifier le pseudo
    player_name = request.form.get("player_name", "").strip()
    if not player_name:
        return jsonify({"ok": False, "error": "player_name is required"}), 400
    if len(player_name) > 64:
        return jsonify({"ok": False, "error": "player_name too long (max 64 chars)"}), 400

    # 3. Parser le fichier .sav
    #    On écrit dans un fichier temporaire car parse_gvas attend un chemin
    #    Le fichier est automatiquement supprimé après le bloc "with"
    try:
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp_path = tmp.name
            file.save(tmp_path)

        try:
            raw_save = parse_gvas(tmp_path)
        finally:
            os.unlink(tmp_path)  # toujours supprimer, même en cas d'erreur

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to parse save file: {str(e)}"
        }), 422

    # 4. Construire les données du dashboard
    try:
        dashboard_data = build_dashboard_data(raw_save, player_name)
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Failed to build dashboard: {str(e)}"
        }), 500

    return jsonify({"ok": True, "data": dashboard_data})


# ── Health check (utile pour Vercel et les monitors) ─────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "drg-dashboard-api"})


# ── Gestion des erreurs globales ──────────────────────────────────────────────

@app.errorhandler(413)
def file_too_large(e):
    return jsonify({
        "ok": False,
        "error": f"File too large (max {MAX_FILE_SIZE_MB}MB)"
    }), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"ok": False, "error": "Method not allowed"}), 405


# ── Lancement local ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("DRG Dashboard API — http://localhost:5000")
    print("Endpoint : POST /api/parse")
    print("           GET  /api/health")
    app.run(debug=True, port=5000)
