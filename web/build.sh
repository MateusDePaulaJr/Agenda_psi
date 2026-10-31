#!/usr/bin/env bash
# Script de build do Render: instala dependências, publica estáticos e aplica migrações.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py criar_usuaria
