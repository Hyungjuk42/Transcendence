import json
from django.core.cache import cache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class GameRoomManager:
	@staticmethod
	def create_room(room_name, mode, password=None):
		room_number = GameRoomManager.get_next_room_number()
		room_size = GameRoomManager.get_room_size(mode)
		room_data = {
			'room_number': room_number,
			'room_name': room_name,
			'room_size': room_size,
			'password': password,
			'current_players': 0,
		}
		room_data_json_str = json.dumps(room_data)
		cache.set(f'game_room_{room_number}', room_data_json_str)
		room_data_json = json.loads(room_data_json_str)
		GameRoomManager.send_room_list_channel_group()
		return room_data_json

	@staticmethod
	def get_room(room_number):
		room_data = cache.get(f'game_room_{room_number}')
		if room_data:
			return room_data
		return None

	@staticmethod
	def add_player(room_number):
		room_data = GameRoomManager.get_room(room_number)
		room_data_dict = json.loads(room_data)
		if room_data_dict:
			if room_data_dict['current_players'] < room_data_dict['room_size']:
				room_data_dict['current_players'] += 1
				cache.set(f'game_room_{room_number}', json.dumps(room_data_dict))
				GameRoomManager.send_room_list_channel_group()
			else:
				raise Exception('Room is full')
		else:
			raise Exception('Room does not exist')

	@staticmethod
	def remove_player(room_number):
		room_data = GameRoomManager.get_room(room_number)
		if room_data:
			if room_data['current_players'] == 0:
				raise Exception('Room is empty')
			elif room_data['current_players'] > 0:
				room_data['current_players'] -= 1
				if room_data['current_players'] == 0:
					cache.delete(f'game_room_{room_number}')
				else:
					cache.set(f'game_room_{room_number}', json.dumps(room_data))
				GameRoomManager.send_room_list_channel_group()
		else:
			raise Exception('Room does not exist')

	@staticmethod
	def get_all_rooms():
		keys = cache.keys('game_room_*')
		sorted_keys = sorted(keys, key=lambda x: int(x.split('_')[-1]))
		rooms = []
		for key in sorted_keys:
			room_data = cache.get(key)
			if room_data:
				rooms.append(json.loads(room_data))
		return rooms

	@staticmethod
	def send_room_list_channel_group():
		rooms = GameRoomManager.get_all_rooms()
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			'room_lounge',
			{
				'game_rooms': rooms,
			}
		)

	@staticmethod
	def get_next_room_number():
		keys = cache.keys('game_room_*')
		if not keys:
			return 1

		existing_numbers = sorted(int(key.split('_')[-1]) for key in keys)
		for i in range(1, len(existing_numbers) + 1):
			if i not in existing_numbers:
				return i

		return existing_numbers[-1] + 1

	@staticmethod
	def get_room_size(mode):
		if mode == '1v1' or mode == '1vs1':
			return 2
		elif mode == 'tournament' or mode == 'Tournament':
			return 4
		else:
			return 0
