
from django.urls import path
from .views import CreateGameRoomView

urlpatterns = [
	path("rooms/", CreateGameRoomView.as_view(), name="create_game_room"),
]
