web: python manage.py migrate --no-input && python manage.py seed_uiventures && gunicorn uiventures_crm.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
