"""WSGI config for UI Ventures Retail CRM System."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "uiventures_crm.settings")
application = get_wsgi_application()
