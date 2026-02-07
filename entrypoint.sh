#!/bin/bash
set -e

echo "Running migrations..."
python -c "
from cairn.config import load_config
from cairn.storage.database import Database
config = load_config()
db = Database(config.db)
db.connect()
db.run_migrations()
db.close()
"
echo "Migrations complete. Ready."

exec "$@"
