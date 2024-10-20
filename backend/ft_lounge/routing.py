from django.urls import path
from . import consumers

websocket_urlpatterns = [
	path(r"ws/game/rooms/", consumers.GameLoungeConsumer.as_asgi()),
]
