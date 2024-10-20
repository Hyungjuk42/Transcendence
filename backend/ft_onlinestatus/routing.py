from django.urls import path
from . import consumers

websocket_urlpatterns = [
	path(r"ws/online/", consumers.StatusConsumer.as_asgi()),
]