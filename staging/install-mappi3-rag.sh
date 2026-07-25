#!/usr/bin/env bash
set -euo pipefail

# Install/stage MapPI3 Offline RAG on the live Pi.
# Intended to run ON the Pi from the extracted staging bundle.
# No systemd service is installed by default; this only places files, indexes docs,
# and writes a tiny config wrapper. Rollback restores prior /opt + /var paths.

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/opt/mappi3/backups/rag-install-${TS}"
RAG_DIR="/opt/mappi3/rag"
DOC_DIR="/opt/mappi3/rag/docs"
DB_DIR="/var/lib/mappi3/rag"
OLLAMA_HOST_DEFAULT="${MAPPI3_RAG_OLLAMA:-http://10.42.0.38:11434}"
MODEL_DEFAULT="${MAPPI3_RAG_MODEL:-all-minilm}"

sudo mkdir -p "$BACKUP_DIR"
if [ -d "$RAG_DIR" ]; then sudo cp -a "$RAG_DIR" "$BACKUP_DIR/rag.before"; fi
if [ -d "$DB_DIR" ]; then sudo cp -a "$DB_DIR" "$BACKUP_DIR/rag-db.before"; fi

sudo mkdir -p "$RAG_DIR" "$DOC_DIR" "$DB_DIR"
sudo cp staging/mappi3_offline_rag_whisplay.py "$RAG_DIR/mappi3_offline_rag_whisplay.py"
sudo chmod 0755 "$RAG_DIR/mappi3_offline_rag_whisplay.py"

# Copy compact reference docs. These are safe text docs, not model weights.
if [ -d offline-library/references ]; then
  sudo rm -rf "$DOC_DIR/offline-library-references"
  sudo mkdir -p "$DOC_DIR/offline-library-references"
  sudo cp -a offline-library/references/. "$DOC_DIR/offline-library-references/"
fi
if [ -d docs ]; then
  sudo rm -rf "$DOC_DIR/app-docs"
  sudo mkdir -p "$DOC_DIR/app-docs"
  sudo cp -a docs/. "$DOC_DIR/app-docs/"
fi

sudo tee "$RAG_DIR/run-rag-once" >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail
QUERY="\${*:-}"
if [ -z "\$QUERY" ]; then
  echo "Usage: run-rag-once <question>" >&2
  exit 2
fi
exec python3 "$RAG_DIR/mappi3_offline_rag_whisplay.py" \
  --docs "$DOC_DIR/offline-library-references" "$DOC_DIR/app-docs" \
  --db "$DB_DIR/reference_vectors.sqlite3" \
  --ollama "\${MAPPI3_RAG_OLLAMA:-$OLLAMA_HOST_DEFAULT}" \
  --model "\${MAPPI3_RAG_MODEL:-$MODEL_DEFAULT}" \
  --once "\$QUERY"
EOF
sudo chmod 0755 "$RAG_DIR/run-rag-once"

# Build or refresh the index. If NukeBox/Ollama is unavailable, the Python script
# intentionally falls back to keyword-only indexing instead of failing.
sudo python3 "$RAG_DIR/mappi3_offline_rag_whisplay.py" \
  --docs "$DOC_DIR/offline-library-references" "$DOC_DIR/app-docs" \
  --db "$DB_DIR/reference_vectors.sqlite3" \
  --ollama "$OLLAMA_HOST_DEFAULT" \
  --model "$MODEL_DEFAULT" \
  --rebuild \
  --once "wild mushroom safe eat photo"

echo "MAPPI3_RAG_INSTALL_OK"
echo "BACKUP_DIR=$BACKUP_DIR"
echo "RAG_DIR=$RAG_DIR"
echo "DB=$DB_DIR/reference_vectors.sqlite3"
echo "ROLLBACK: sudo rm -rf '$RAG_DIR' '$DB_DIR'; [ -d '$BACKUP_DIR/rag.before' ] && sudo cp -a '$BACKUP_DIR/rag.before' '$RAG_DIR'; [ -d '$BACKUP_DIR/rag-db.before' ] && sudo cp -a '$BACKUP_DIR/rag-db.before' '$DB_DIR'"
