import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

class LobbyConsumer(AsyncWebsocketConsumer):
    rooms = {}
    matchmaking_queue = []
    match_user_roomid = {}
    room_id = 0
    lock = asyncio.Lock()

    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.close()
            return
        await self.channel_layer.group_add("lobby", self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'room_list',
            'rooms': list(LobbyConsumer.rooms.values())
        }))

    async def disconnect(self, close_code):
        
        if self.scope['user'].is_anonymous:
            return
        
        if self.scope['user'].username in LobbyConsumer.matchmaking_queue:
            LobbyConsumer.matchmaking_queue.remove(self.scope['user'].username)
        await self.channel_layer.group_discard("lobby", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'create_room':
            room_id = await self.get_room_id()
            room_info = {
                'room_name': data['room_name'],
                'room_id': room_id,
                'mode': data['mode'],
                'is_secret': data['is_secret'],
                'is_custom': data['is_custom'],
                'password': data.get('password', ''),
                'players': [],
                'in_game_players': [],
                'status': 'room',
            }
            LobbyConsumer.rooms[room_id] = room_info
            await self.send(text_data=json.dumps({
                'type': 'room_created',
                'room_id': room_id,
            }))
            await self.update_room_list()
        elif data['type'] == 'join_room':
            room_id = data['room_id']
            if room_id in LobbyConsumer.rooms:
                if LobbyConsumer.rooms[room_id]['status'] != 'room':
                    await self.send(text_data=json.dumps({
                        'type': 'join_denied',
                        'message': 'This room is already playing a game.',
                    }))
                elif len(LobbyConsumer.rooms[room_id]['players']) >= LobbyConsumer.rooms[room_id]['mode']:
                    await self.send(text_data=json.dumps({
                        'type': 'join_denied',
                        'message': 'Room is full.',
                    }))
                elif LobbyConsumer.rooms[room_id]['is_secret']:
                    await self.send(text_data=json.dumps({
                        'type': 'password_required',
                        'room_id': room_id,
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'join_approved',
                        'room_id': room_id,
                    }))
            else:
                await self.send(text_data=json.dumps({
                    'type': 'join_denied',
                    'message': 'Room does not exist.',
                }))
        elif data['type'] == 'join_secret_room':
            room_id = data['room_id']
            if room_id in LobbyConsumer.rooms:
                if data['password'] == LobbyConsumer.rooms[room_id]['password']:
                    await self.send(text_data=json.dumps({
                        'type': 'join_approved',
                        'room_id': room_id,
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'join_denied',
                        'message': 'Wrong password.',
                    }))
        elif data['type'] == 'matchmaking':
            await self.matchmaking()
        elif data['type'] == 'cancel_matchmaking':
            username = self.scope['user'].username
            if username in LobbyConsumer.matchmaking_queue:
                LobbyConsumer.matchmaking_queue.remove(username)
                await self.send(text_data=json.dumps({
                    'type': 'matchmaking_cancelled',
                }))
            
    async def matchmaking(self):
        username = self.scope['user'].username
        if username in LobbyConsumer.matchmaking_queue:
            await self.send(text_data=json.dumps({
                'type': 'matchmaking_waiting',
            }))
            return
        LobbyConsumer.matchmaking_queue.append(username)
        await self.send(text_data=json.dumps({
            'type': 'matchmaking_waiting',
        }))
        await self.check_matchmaking()

    async def check_matchmaking(self):
        while len(LobbyConsumer.matchmaking_queue) >= 2:
            player1 = LobbyConsumer.matchmaking_queue.pop(0)
            player2 = LobbyConsumer.matchmaking_queue.pop(0)
            room_id = await self.get_room_id()
            room_info = {
                'room_name': 'Matchmaking Room',
                'room_id': room_id,
                'mode': 'matchmaking',
                'is_secret': False,
                'is_custom': False,
                'players': [],
                'in_game_players': [player1, player2],
                'status': 'game',
            }
            LobbyConsumer.match_user_roomid[player1] = room_id
            LobbyConsumer.match_user_roomid[player2] = room_id
            LobbyConsumer.rooms[room_id] = room_info
            await self.channel_layer.group_send(
                "lobby",
                {
                    'type': 'goto_matchmaking_game',
                    'room_id': room_id,
                }
            )
   
    async def update_room_list(self):
        await self.channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    async def room_list_update(self, event):
        rooms = event['rooms']
        await self.send(text_data=json.dumps({
            'type': 'room_list',
            'rooms': rooms
        }))

    async def goto_matchmaking_game(self, event):
        current_user = self.scope['user'].username
        if current_user in LobbyConsumer.match_user_roomid:
            await self.send(text_data=json.dumps({
                'type': 'goto_matchmaking_game',
                'room_id': event['room_id'],
            }))
            del LobbyConsumer.match_user_roomid[current_user]
    
    @classmethod        
    async def get_room_id(cls):
        async with cls.lock:
            cls.room_id += 1
            return cls.room_id