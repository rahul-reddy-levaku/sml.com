import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spoorthi_macs.settings')
application = get_wsgi_application()
