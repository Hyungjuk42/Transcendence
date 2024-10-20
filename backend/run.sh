#!/bin/sh

find . | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf
find ./*/migrations/ -type f ! -name '__init__.py' -exec rm -f {} +
python manage.py makemigrations
python manage.py migrate
touch /code/log/django_error.log
gunicorn backend.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --logger-class backend.logger.UniformLogger