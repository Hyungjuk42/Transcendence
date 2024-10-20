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
import uuid


class StatusConsumer(AsyncWebsocketConsumer):
	room_created = False
	user_list = []
	update_need_user = []

	async def connect(self):
		user = self.scope['user']
		if user.is_anonymous:
			await self.accept()
			await self.close()
			return
		username = self.scope['user'].username
		await self.accept()
		self.check = False
		self.uuid = uuid.uuid4()
		await self.channel_layer.group_add(
			'online_status',
			self.channel_name,
		)
  
		if username in self.user_list:
			await self.channel_layer.group_send(
				'online_status',
				{
					'type': 'old_out',
					'username': username,
					'uuid': self.uuid,
				}
			)
			return
       
		await self.channel_layer.group_send(
			'online_status',
			{
				'type': 'global_list',
				'username': self.user_list,
				'new_online': username,
				'new_offline': '',
				'new_uid': self.scope['user'].uid,
			}
		)
		self.user_list.append(username)
  
  
	async def old_out(self, event):
		if self.scope['user'].username == event['username'] and self.uuid != event['uuid']:
			await self.send(text_data=json.dumps({
				'type': 'duplicate_login',
			}))
			self.check = True
			await self.close()
			return
     
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
				'new_uid': self.scope['user'].uid,
			}
		)

	async def global_list(self, event):
		user = self.scope['user'].username
		user = CustomUser.objects.get(username=user)
		user_list = event['username']
		friend_list = FollowList.objects.filter(user=user).values_list('following_user', flat=True)
		friend_list2 = []
		for ppl in friend_list:
			friend_list2.append(CustomUser.objects.get(uid=ppl).username)
		online_list = []
		offline_list = []
		if event['new_online'] != '': # 새로운 유저가 온라인으로 들어왔다면
			if event['new_online'] == user.username:  # 그 새로운유저가 자기 자신채널이라면 그땐 새로 리스트 전부 보내주기
				for man in friend_list2:
					user_info = await self.make_dictionary(CustomUser.objects.get(username=man))
					if man in user_list:
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
				user_info = await self.make_dictionary(CustomUser.objects.get(uid=event['new_uid']))
				if event['new_online'] in friend_list2:
					online_list.append(user_info)
					await self.send(text_data=json.dumps({
						'type': 'add_online',
						'online': online_list,
					}))
		else:	
			user_info = await self.make_dictionary(CustomUser.objects.get(uid=event['new_uid']))
			if event['new_offline'] in friend_list2:
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
			friend_list2 = []
			for ppl in friend_list:
				friend_list2.append(CustomUser.objects.get(uid=ppl).username)
			for man in friend_list2:
				user_info = await self.make_dictionary(CustomUser.objects.get(username=man))
				if man in self.user_list:
					online_list.append(user_info)
				else:
					offline_list.append(user_info)
			await self.send(text_data=json.dumps({
				'type': 'status',
				'online': online_list,
				'offline': offline_list,
			}))
		elif data['type'] == 'change_name':
			self.user_list.remove(self.scope['user'].username)
			self.user_list.append(data['new_name'])
			old_name = self.scope['user'].username
			self.scope['user'].username = data['new_name']
			await self.channel_layer.group_send(
				'online_status',
				{
					'type': 'change_name',
					'old_name': old_name,
					'new_name': data['new_name'],
					'user_uid': self.scope['user'].uid,
				}
			)

	async def change_name(self, event):
		me = CustomUser.objects.get(uid=self.scope['user'].uid)
		friend_list = FollowList.objects.filter(user=me).values_list('following_user', flat=True)
		friend_list2 = []
		for ppl in friend_list:
			friend_list2.append(CustomUser.objects.get(uid=ppl).username)
		if event['old_name'] in friend_list2:
			friend_list2.remove(event['old_name'])
			friend_list2.append(event['new_name'])
		online_list = []
		offline_list = []
		for man in friend_list2:
			user_info = await self.make_dictionary(CustomUser.objects.get(username=man))
			if man in self.user_list:
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
