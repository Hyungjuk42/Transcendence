import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
import django
django.setup()
import json
import asyncio
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from ft_user.models import CustomUser, FollowList


class StatusConsumer(AsyncWebsocketConsumer):
	room_created = False
	user_list = []
	update_need_user = []

	async def connect(self):
		user = self.scope['user']
		if user.is_anonymous:
			await self.close()
			return
		username = self.scope['user'].username
		await self.accept()
		self.check = False
		# if username in self.user_list:
		# 	await self.send(text_data=json.dumps({
		# 		'type': 'duplicate_login',
		# 	}))
		# 	self.check = True
		# 	await self.close()
		# 	return

		await self.channel_layer.group_add(
			'online_status',
			self.channel_name,
		)
		await self.channel_layer.group_send(
			'online_status',
			{
				'type': 'global_list',
				'username': self.user_list,
				'new_online': username,
				'new_offline': '',
			}
		)
		self.user_list.append(username)

	async def disconnect(self, close_code):
		if self.scope['user'].is_anonymous:
			return
		username = self.scope['user'].username
		if self.check :
			await self.channel_layer.group_discard(
				'online_status',
				self.channel_name,
			)
			return
		self.user_list.remove(username)
		await self.channel_layer.group_discard(
			'online_status',
			self.channel_name,
		)
		await self.channel_layer.group_send(
			'online_status',
			{
				'type': 'global_list',
				'username': self.user_list,
				'new_online': '',
				'new_offline': username,
			}
		)

	async def global_list(self, event):
		user = self.scope['user'].username
		user = CustomUser.objects.get(username=user)
		user_list = event['username']
		friend_list = FollowList.objects.filter(user=user).values_list('following_user', flat=True)
		for ppl in friend_list:
			ppl = ppl.username
		online_list = []
		offline_list = []
		if event['new_online'] != '': # 새로운 유저가 온라인으로 들어왔다면
			if event['new_online'] == user.username:  # 그 새로운유저가 자기 자신채널이라면 그땐 새로 리스트 전부 보내주기
				for user_id in friend_list:
					user_info = await self.make_dictionary(CustomUser.objects.get(uid=user_id))
					user_name = user_info['username']
					if user_name in user_list:
						online_list.append(user_info)
					else:
						offline_list.append(user_info)
				await self.send(text_data=json.dumps({
					'type': 'status',
					'online': online_list,
					'offline': offline_list,
				}))
				return
			else:  # 다른유저들은 새로들어온유저가 친구일때 그 친구의 정보만 보내주기
				user_info = await self.make_dictionary(CustomUser.objects.get(username=event['new_online']))
				if event['new_online'] in friend_list:
					online_list.append(user_info)
					await self.send(text_data=json.dumps({
						'type': 'add_online',
						'online': online_list,
					}))
		else:
			user_info = await self.make_dictionary(CustomUser.objects.get(username=event['new_offline']))
			if event['new_offline'] in friend_list:
				offline_list.append(user_info)
				await self.send(text_data=json.dumps({
					'type': 'add_offline',
					'offline': offline_list
				}))

	async def receive(self, text_data):
		data = json.loads(text_data)
		if data['type'] == 'update':
			online_list = []
			offline_list = []
			user = self.scope['user'].username
			user = CustomUser.objects.get(username=user)
			friend_list = FollowList.objects.filter(user=user).values_list('following_user', flat=True)
			for user_id in friend_list:
				user_info = await self.make_dictionary(CustomUser.objects.get(uid=user_id))
				user_name = user_info['username']
				if user_name in self.user_list:
					online_list.append(user_info)
				else:
					offline_list.append(user_info)
			await self.send(text_data=json.dumps({
				'type': 'status',
				'online': online_list,
				'offline': offline_list,
			}))

	async def make_dictionary(self, user):
		return ({
			'username': user.username,
			'win': user.win,
			'lose': user.lose,
			'profile_image': user.profile_image.url if user.profile_image else None,
		})
