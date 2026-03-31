"""
ASGI config for api_acqm project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_acqm.settings')

application = get_asgi_application()
