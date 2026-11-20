"""ASGI config for UI Ventures Retail CRM System."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "uiventures_crm.settings")
application = get_asgi_application()
