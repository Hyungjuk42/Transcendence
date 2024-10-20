"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import ft_game.routing
import ft_lobby.routing
import ft_room.routing
import ft_onlinestatus.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            ft_game.routing.websocket_urlpatterns +
            ft_lobby.routing.websocket_urlpatterns +
            ft_room.routing.websocket_urlpatterns +
			      ft_onlinestatus.routing.websocket_urlpatterns
        )
    ),
})
