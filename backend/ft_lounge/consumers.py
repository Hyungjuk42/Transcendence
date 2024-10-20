import json
from django.core.cache import cache
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer, AsyncWebsocketConsumer
from channels.layers import get_channel_layer


class GameLoungeConsumer(WebsocketConsumer):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.room_number = None
		self.room_group_name = None

	def connect(self):
		self.room_group_name = 'room_lounge'
		# join the room group
		async_to_sync(self.channel_layer.group_add)(
			self.room_group_name,
			self.channel_name,
		)
		# connection has to be accepted
		self.accept()
		# send room list to group
		self.send_game_room_list()

	def disconnect(self, close_code):
		# leave the room group
		async_to_sync(self.channel_layer.group_discard)(
			self.room_group_name,
			self.channel_name,
		)

	def send_game_room_list(self):
		from .manager import GameRoomManager
		game_rooms = GameRoomManager.get_all_rooms()
		self.send(text_data=json.dumps({
			'game_rooms': game_rooms,
		}))

