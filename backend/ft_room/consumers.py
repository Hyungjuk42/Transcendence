import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from ft_lobby.consumers import LobbyConsumer
import asyncio



class RoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):

        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.close()
            return
        self.room_id_str = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'room_{self.room_id_str}'
        self.room_id = int(self.room_id_str)
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        #방이 없으면 그냥 종료
        if self.room_id not in LobbyConsumer.rooms:
            await self.send(text_data=json.dumps({
                'type': 'room_not_exist',
            }))
            return
        
        
        
        # 방이 꽉 찼으면 연결 종료
        if len(LobbyConsumer.rooms[self.room_id]['players']) >= LobbyConsumer.rooms[self.room_id]['mode']:
            await self.send(text_data=json.dumps({
                'type': 'room_full',
            }))
            await self.close()
            return
        
        # 방 상태가 room이 아니면 연결 종료
        if LobbyConsumer.rooms[self.room_id]['status'] != 'room':
            await self.send(text_data=json.dumps({
                'type': 'room_not_exist',
            }))
            await self.close()
            return
        
        LobbyConsumer.rooms[self.room_id]['players'].append(self.scope['user'].username)
        await self.update_room_list()
        
        await self.send(text_data=json.dumps({
            'type': 'room_info',
            'room_name': LobbyConsumer.rooms[self.room_id]['room_name'],
            'room_id': self.room_id,
            'mode': LobbyConsumer.rooms[self.room_id]['mode'],
            'is_custom': LobbyConsumer.rooms[self.room_id]['is_custom'],
            'user_list': LobbyConsumer.rooms[self.room_id]['players'],
        }))

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'connect_user',
                'new_user': self.scope['user'].username,
            }
        )
        if len(LobbyConsumer.rooms[self.room_id]['players']) == LobbyConsumer.rooms[self.room_id]['mode']:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'room_ready',
                }
            )
        return
        
        

    async def disconnect(self, close_code):
        if self.scope['user'].is_anonymous:
            return
    
        if self.room_id not in LobbyConsumer.rooms: # 방이 없어졌으면 그냥 종료
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return
        
        if self.scope['user'].username in LobbyConsumer.rooms[self.room_id]['players']:
            LobbyConsumer.rooms[self.room_id]['players'].remove(self.scope['user'].username)
        
        # 게임상태가 game이면 폭파나 연결 끊기 메세지를 보내지 않음
        if LobbyConsumer.rooms[self.room_id]['status'] == 'game' or LobbyConsumer.rooms[self.room_id]['status'] == 'playing':
            await self.update_room_list()
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        username = self.scope['user'].username
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'disconnect_user',
                'disconnected_user': self.scope['user'].username,
            }
        )
        
        await self.update_room_list()
        
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        return

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            LobbyConsumer.rooms[self.room_id]['status'] = 'game'
            LobbyConsumer.rooms[self.room_id]['in_game_players'].append(LobbyConsumer.rooms[self.room_id]['players'][0])
            LobbyConsumer.rooms[self.room_id]['in_game_players'].append(LobbyConsumer.rooms[self.room_id]['players'][1])
            if LobbyConsumer.rooms[self.room_id]['mode'] == 4:
                LobbyConsumer.rooms[self.room_id]['in_game_players'].append(LobbyConsumer.rooms[self.room_id]['players'][2])
                LobbyConsumer.rooms[self.room_id]['in_game_players'].append(LobbyConsumer.rooms[self.room_id]['players'][3])
            
            if LobbyConsumer.rooms[self.room_id]['is_custom']:
                if 'goal_score' in data:
                    LobbyConsumer.rooms[self.room_id]['goal_score'] = data['goal_score']
                if 'items' in data:
                    LobbyConsumer.rooms[self.room_id]['items'] = data['items']
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'goto_game',
                    'room_id': self.room_id,
                }
            )
            await self.update_room_list()
        elif data['type'] == 'disconnect':
            await self.close()

            

    async def update_room_list(self):
        channel_layer = get_channel_layer()
        # 게임중인 방은 제외
        # 룸안에 유저가 없으면 방을 삭제
        if not LobbyConsumer.rooms[self.room_id]['players'] and LobbyConsumer.rooms[self.room_id]['status'] != 'game' and LobbyConsumer.rooms[self.room_id]['status'] != 'playing':
            del LobbyConsumer.rooms[self.room_id]
        await channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    async def chat_message(self, event):
        message = event['message']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message
        }))

    async def room_destroyed(self, event):
        await self.send(text_data=json.dumps({
            'type': 'room_destroyed'
        }))
        
    async def connect_user(self, event):
        new_user = event['new_user']
        
        await self.send(text_data=json.dumps({
            'type': 'connect_user',
            'new_user': new_user,
            'room_name': LobbyConsumer.rooms[self.room_id]['room_name'],
            'room_id': self.room_id,
            'mode': LobbyConsumer.rooms[self.room_id]['mode'],
            'user_list': LobbyConsumer.rooms[self.room_id]['players'],
            'is_custom': LobbyConsumer.rooms[self.room_id]['is_custom'],
        }))
        
    async def disconnect_user(self, event):
        disconnected_user = event['disconnected_user']
        
        await self.send(text_data=json.dumps({
            'type': 'disconnect_user',
            'disconnected_user': disconnected_user,
            'room_name': LobbyConsumer.rooms[self.room_id]['room_name'],
            'room_id': self.room_id,
            'mode': LobbyConsumer.rooms[self.room_id]['mode'],
            'user_list': LobbyConsumer.rooms[self.room_id]['players'],
            'is_custom': LobbyConsumer.rooms[self.room_id]['is_custom'],
        }))
        
    async def room_ready(self, event):
        
        await self.send(text_data=json.dumps({
            'type': 'room_ready',
            'you': self.scope['user'].username,
            'host': LobbyConsumer.rooms[self.room_id]['players'][0],
        }))
    
    async def goto_game(self, event):
        room_id = event['room_id']
        await self.send(text_data=json.dumps({
            'type': 'goto_game',
            'mode': LobbyConsumer.rooms[room_id]['mode'],
            'room_id': room_id,
            'is_custom': LobbyConsumer.rooms[room_id]['is_custom'],
        }))