import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
import django
django.setup()
import json
import asyncio
import random
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from ft_lobby.consumers import LobbyConsumer
from ft_user.models import CustomUser, SingleGameRecord, MultiGameRecord, SingleGameDetail
from asgiref.sync import sync_to_async
from pprint import pprint
import math

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'anonymous user'
            }))
            await self.close()
            return
        
        
        self.room_id_str = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = self.room_id_str
        self.room_id = int(self.room_id_str)
        self.status = 'waiting'
        self.ball_count = 0
        self.past_ball_position = []

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        if self.room_id not in LobbyConsumer.rooms:
            await self.send_error_message('Room does not exist')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['status'] != 'game':
            await self.send_error_message('Room is not in game status')
            await self.close()
            return

        if self.scope['user'].username not in LobbyConsumer.rooms[self.room_id]['in_game_players']:
            await self.send_error_message('You are not in game')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['mode'] != 'matchmaking' and \
            LobbyConsumer.rooms[self.room_id]['mode'] != 2:
            await self.send_error_message('Room is not in matchmaking mode')
            await self.close()
            return

        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            LobbyConsumer.rooms[self.room_id]['game'] = {
                'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                'player_bar': {'left': 360, 'right': 360},
                'scores': {'left': 0, 'right': 0},
                'players': [],
                'roles': {},
                'bar_move': {'left': 0, 'right': 0},
                'record': [],
            }

        LobbyConsumer.rooms[self.room_id]['game']['players'].append(self.scope['user'].username)
        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 2:
            LobbyConsumer.rooms[self.room_id]['game']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['in_game_players'][0],
                'right': LobbyConsumer.rooms[self.room_id]['in_game_players'][1],
            }
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            LobbyConsumer.rooms[self.room_id]['status'] = 'playing'
        self.game = LobbyConsumer.rooms[self.room_id]['game']

    async def send_error_message(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
        self.status = 'connect error'

    async def disconnect(self, close_code):
        if self.scope['user'].is_anonymous:
            
            return
        
        if self.room_id not in LobbyConsumer.rooms:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'connect error':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        if self.status == 'playing' or self.status == 'waiting':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': 'user disconnected'
                }
            )
            LobbyConsumer.rooms[self.room_id]['game']['players'].remove(self.scope['user'].username)
            # 부전승 나는 경우 => 한 명이 일방적으로 나감
            if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 1:
                winner_name = LobbyConsumer.rooms[self.room_id]['game']['players'][0]
                loser_name = self.scope['user'].username
                game_data = await get_game_data(winner_name, loser_name, 99, 0)
                await create_game_records(game_data, is_tournament=False, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['record'])
            elif len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 0:
                del LobbyConsumer.rooms[self.room_id]
            await self.update_room_list()

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            if self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game']['players']) != 2:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'error',
                        'message': 'Not enough players'
                    }
                )
                return
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and self.scope['user'].username == LobbyConsumer.rooms[self.room_id]['game']['roles']['left']:
                asyncio.create_task(self.start_ball_movement())
        elif data['type'] == 'move_bar':
            self.update_bar_position(data['direction'], data['role'])
        elif data['type'] == 'stop_bar':
            self.game['bar_move'][data['role']] = 0

    async def start_ball_movement(self):
        while self.status == 'playing' and self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 2:
            self.update_ball_position()
            self.ball_count += 1
            self.past_ball_position.append(self.game['ball'].copy()) 
            if len(self.past_ball_position) > 33:
                self.past_ball_position.pop(0)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'update_game',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            await asyncio.sleep(0.03)

    def update_ball_position(self):
        self.game['player_bar']['left'] = max(0, min(720, self.game['player_bar']['left'] + self.game['bar_move']['left']))
        self.game['player_bar']['right'] = max(0, min(720, self.game['player_bar']['right'] + self.game['bar_move']['right']))
        if -19 < self.game['ball']['speedX'] < 19 and -39 < self.game['ball']['speedY'] < 39:
            self.game['ball']['speedX'] *= 1.02
            self.game['ball']['speedY'] *= 1.02
        self.game['ball']['x'] += self.game['ball']['speedX']
        self.game['ball']['y'] += self.game['ball']['speedY']
        # 위 야래 벽에 부딪히면 방향 바꾸기
        if self.game['ball']['y'] + self.game['ball']['radius'] > 900 or self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['speedY'] = -self.game['ball']['speedY']
        
        if self.game['ball']['y'] + self.game['ball']['radius'] > 900:
            self.game['ball']['y'] = 900 - self.game['ball']['radius']
        elif self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['y'] = self.game['ball']['radius']
        
        # 왼쪽 player bar에 부딪히면 방향 바꾸기
        if 20 < self.game['ball']['x'] - self.game['ball']['radius'] < 40:
            if self.game['ball']['y'] > self.game['player_bar']['left'] and self.game['ball']['y'] < self.game['player_bar']['left'] + 180:
                degree = (self.game['player_bar']['left'] + 90 - self.game['ball']['y']) * 8 / 9
                self.game['ball']['speedY'] = math.tan(math.radians(-degree)) * 5
                self.game['ball']['speedX'] = 5
        # 오른쪽 player bar에 부딪히면 방향 바꾸기
        if 1160 < self.game['ball']['x'] + self.game['ball']['radius'] < 1180:
            if self.game['ball']['y'] > self.game['player_bar']['right'] and self.game['ball']['y'] < self.game['player_bar']['right'] + 180:
                degree = (self.game['player_bar']['right'] + 90 - self.game['ball']['y']) * 8 / 9
                self.game['ball']['speedY'] = math.tan(math.radians(degree)) * (-5)
                self.game['ball']['speedX'] = -5
        # 왼쪽, 오른쪽 벽에 부딪히면 점수 올리기
        if (self.game['ball']['x'] - self.game['ball']['radius'] < 0) or (self.game['ball']['x'] + self.game['ball']['radius'] > 1200):
            if self.game['ball']['x'] - self.game['ball']['radius'] < 0:
                self.game['scores']['right'] += 1
                self.record_goal('right')
            else:
                self.game['scores']['left'] += 1
                self.record_goal('left')
            asyncio.create_task(self.broadcast_scores())
            asyncio.create_task(self.check_game_over())
            self.reset_ball()

    def record_goal(self, goal_user_position):
        self.game['record'].append({
            'goal_user_name': self.game['roles'][goal_user_position],
            'goal_user_position': goal_user_position,
            'ball_start_position': self.past_ball_position[0].copy(),
            'ball_end_position': self.game['ball'].copy(),
            'timestamp': self.ball_count
        })

    def reset_ball(self):
        self.game['ball']['x'] = 600
        self.game['ball']['y'] = 450
        self.game['ball']['speedX'] = 10 * (1 if random.random() > 0.5 else -1)
        self.game['ball']['speedY'] = 10 * (1 if random.random() > 0.5 else -1)

    async def broadcast_scores(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_game',
                'game': self.game,
            }
        )

    async def check_game_over(self):
        if self.game['scores']['left'] >= 3:
            await self.game_end('left', 'right')
        elif self.game['scores']['right'] >= 3:
            await self.game_end('right', 'left')

    async def game_end(self, winner, loser):
        self.status = 'game_over'
        LobbyConsumer.rooms[self.room_id]['status'] = 'room'
        LobbyConsumer.rooms[self.room_id]['in_game_players'] = []
        winner_username = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
        loser_username = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
        winner_score = self.game['scores'][winner]
        loser_score = self.game['scores'][loser]
        game_data = await get_game_data(winner_username, loser_username, winner_score, loser_score)
        await create_game_records(game_data, is_tournament=False, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['record'])
        del LobbyConsumer.rooms[self.room_id]['game']
        if LobbyConsumer.rooms[self.room_id]['mode'] == 'matchmaking':
            del LobbyConsumer.rooms[self.room_id]
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_over',
                'winner': winner_username,
                'loser': loser_username,
            }
        )
        await self.update_room_list()

    async def update_room_list(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    def update_bar_position(self, direction, role):
        if direction == 'up':
            self.game['bar_move'][role] = -20
        elif direction == 'down':
            self.game['bar_move'][role] = 20

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'game': event['game'],
            'you': 'left' if self.scope['user'].username == event['game']['roles']['left'] else 'right'
        }))

    async def update_game(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update_game',
            'game': event['game'],
            'you': 'left' if self.scope['user'].username == event['game']['roles']['left'] else 'right'
        }))

    async def game_over(self, event):
        self.status = 'game_over'
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'loser': event['loser'],
            'room_id': self.room_id
        }))

    async def error(self, event):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))

async def create_game_records(game_data, is_tournament=False, game_record_details=None):
    game_record = await sync_to_async(SingleGameRecord.objects.create)(
        player1=game_data['player1'],
        player1_score=game_data['player1_score'],
        player2=game_data['player2'],
        player2_score=game_data['player2_score'],
        is_tournament=is_tournament
    )
    for record_detail in game_record_details:
        ball_start_position = json.dumps(record_detail['ball_start_position'])
        ball_end_position = json.dumps(record_detail['ball_end_position'])
        
        SingleGameDetail.objects.create(
            game=game_record,
            goal_user_name=record_detail['goal_user_name'],
            goal_user_position=record_detail['goal_user_position'],
            ball_start_position=ball_start_position,
            ball_end_position=ball_end_position,
            timestamp=record_detail['timestamp'] * 0.03
        )
    return game_record.id


async def get_game_data(player1_name, player2_name, player1_score, player2_score):
    player1 = await sync_to_async(CustomUser.objects.get)(username=player1_name)
    player2 = await sync_to_async(CustomUser.objects.get)(username=player2_name)
    if (player1_score > player2_score):
        await update_user_win_or_lose(player1, player2)
    elif (player1_score < player2_score):
        await update_user_win_or_lose(player2, player1)
    game_data = {
        'player1': player1,
        'player2': player2,
        'player1_score': player1_score,
        'player2_score': player2_score,
    }
    return game_data

    # 동기함수 호출을 비동기 함수로 변경
@sync_to_async
def update_user_win_or_lose(winner, loser):
    winner.win += 1
    winner.save()
    loser.lose += 1
    loser.save()



class TournamentGameConsumer(AsyncWebsocketConsumer):
    game_record_list = {}
    game_player_list = {}
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'anonymous user'
            }))
            await self.close()
            return
        
        self.room_id_str = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = self.room_id_str
        self.room_id = int(self.room_id_str)
        self.status = 'waiting'
        self.ball_count = 0
        self.past_ball_position = []
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        if self.room_id not in LobbyConsumer.rooms:
            await self.send_error_message('Room does not exist')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['status'] != 'game':
            await self.send_error_message('Room is not in game status')
            await self.close()
            return

        if self.scope['user'].username not in LobbyConsumer.rooms[self.room_id]['in_game_players']:
            await self.send_error_message('You are not in game')
            await self.close()
            return
        LobbyConsumer.rooms[self.room_id]['in_game_players'].remove(self.scope['user'].username)
        if LobbyConsumer.rooms[self.room_id]['mode'] != 4:
            await self.send_error_message('Room is not in tournament mode')
            await self.close()
            return
        if self.room_id not in TournamentGameConsumer.game_record_list:
            TournamentGameConsumer.game_record_list[self.room_id] = []
            TournamentGameConsumer.game_player_list[self.room_id] = []
        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            LobbyConsumer.rooms[self.room_id]['game'] = {
                'a' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'record' : [],
                },
                'b' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'record': [],
                },
                'f' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'waiting_players' : [],
                    'record': [],
                },
                'players': [],
                'roles' : {},
                'match' : {},
                'winner_a' : None,
                'winner_b' : None,
                'winner_f' : None,
            }

        LobbyConsumer.rooms[self.room_id]['game']['players'].append(self.scope['user'].username)
        TournamentGameConsumer.game_player_list[self.room_id].append(self.scope['user'].username)

        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 4:
            LobbyConsumer.rooms[self.room_id]['game']['roles'] = {
                LobbyConsumer.rooms[self.room_id]['game']['players'][0]: 'left',
                LobbyConsumer.rooms[self.room_id]['game']['players'][1]: 'right',
                LobbyConsumer.rooms[self.room_id]['game']['players'][2]: 'left',
                LobbyConsumer.rooms[self.room_id]['game']['players'][3]: 'right',
            }
            LobbyConsumer.rooms[self.room_id]['game']['match'] = {
                LobbyConsumer.rooms[self.room_id]['game']['players'][0]: 'a',
                LobbyConsumer.rooms[self.room_id]['game']['players'][1]: 'a',
                LobbyConsumer.rooms[self.room_id]['game']['players'][2]: 'b',
                LobbyConsumer.rooms[self.room_id]['game']['players'][3]: 'b',
            }
            LobbyConsumer.rooms[self.room_id]['game']['a']['players'] = [LobbyConsumer.rooms[self.room_id]['game']['players'][0], LobbyConsumer.rooms[self.room_id]['game']['players'][1]]
            LobbyConsumer.rooms[self.room_id]['game']['b']['players'] = [LobbyConsumer.rooms[self.room_id]['game']['players'][2], LobbyConsumer.rooms[self.room_id]['game']['players'][3]]
            LobbyConsumer.rooms[self.room_id]['game']['a']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['game']['players'][0],
                'right': LobbyConsumer.rooms[self.room_id]['game']['players'][1],
            }
            LobbyConsumer.rooms[self.room_id]['game']['b']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['game']['players'][2],
                'right': LobbyConsumer.rooms[self.room_id]['game']['players'][3],
            }
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            LobbyConsumer.rooms[self.room_id]['status'] = 'playing'
        self.game = LobbyConsumer.rooms[self.room_id]['game']
        await self.update_room_list()

    async def send_error_message(self, message):
        self.status = 'connect error'
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    async def disconnect(self, close_code):
        if self.scope['user'].is_anonymous:
            return
        if self.room_id not in LobbyConsumer.rooms:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'connect error':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'waiting':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': 'user disconnected'
                }
            )

        if LobbyConsumer.rooms[self.room_id]['status'] == 'room':
            del LobbyConsumer.rooms[self.room_id]['game']
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.scope['user'].username in LobbyConsumer.rooms[self.room_id]['game']['players']:
            LobbyConsumer.rooms[self.room_id]['game']['players'].remove(self.scope['user'].username)

        if self.status == 'error':
            del LobbyConsumer.rooms[self.room_id]
            await self.update_room_list()
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 0:
            del LobbyConsumer.rooms[self.room_id]['game']
            await self.update_room_list()
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        match = LobbyConsumer.rooms[self.room_id]['game']['match'][self.scope['user'].username]
        role = LobbyConsumer.rooms[self.room_id]['game']['roles'][self.scope['user'].username]

        if role == 'observer':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        # final 유저가 대기중에 나가는 경우 ex) a매치는 진행중인데 b매치의 승자가 나가는 경우
        if match == 'f':
            if self.scope['user'].username in LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']:
                LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].remove(self.scope['user'].username)
                if len(LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']) == 0:
                    await self.channel_layer.group_discard(
                        self.room_group_name,
                        self.channel_name
                    )
                    return

        # a, b, f매치중 나가는 경우 부전 패 처리
        await self.handle_walkover(match)

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 부전 패 처리
    async def handle_walkover(self, match):
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'].remove(self.scope['user'].username)
        winner = LobbyConsumer.rooms[self.room_id]['game'][match]['players'][0]
        if match != 'f':
            LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].append(winner)
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'] = []
        loser = self.scope['user'].username
        winner_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
        loser_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
        game_data = await get_game_data(winner, loser, 99, 0)
        game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=LobbyConsumer.rooms[self.room_id]['game'][match]['record'])
        TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
        LobbyConsumer.rooms[self.room_id]['game'][match]['scores'][loser_role] = 0
        LobbyConsumer.rooms[self.room_id]['game'][match]['scores'][winner_role] = 99
        if match == 'a':
            LobbyConsumer.rooms[self.room_id]['game']['winner_a'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'left'
            LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        elif match == 'b':
            LobbyConsumer.rooms[self.room_id]['game']['winner_b'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'right'
            LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        elif match == 'f':
            LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
            await self.create_multi_game_records()
        await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'winner': winner,
                    'loser': loser,
                    'score': LobbyConsumer.rooms[self.room_id]['game'][match]['scores'],
                    'match': match,
                }
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'a':
                asyncio.create_task(self.start_ball_movement('a'))
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'b':
                asyncio.create_task(self.start_ball_movement('b'))
        elif data['type'] == 'move_bar':
            self.update_bar_position(data['direction'], data['role'], data['match'])
        elif data['type'] == 'stop_bar':
            self.game[data['match']]['bar_move'][data['role']] = 0
        elif data['type'] == 'final_ready':
            if self.scope['user'].username == self.game['winner_a'] or self.scope['user'].username == self.game['winner_b']:
                LobbyConsumer.rooms[self.room_id]['game']['f']['players'].append(self.scope['user'].username)
            if len(LobbyConsumer.rooms[self.room_id]['game']['f']['players']) == 2:
                if len(LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']) != 2:
                    # 이때가 f 매치 부전승 처리
                    winner = self.scope['user'].username
                    loser = LobbyConsumer.rooms[self.room_id]['game']['f']['players'][0]
                    game_data = await get_game_data(winner, loser, 99, 0)
                    game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['f']['record'])
                    TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
                    winner_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
                    loser_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
                    LobbyConsumer.rooms[self.room_id]['game']['f']['scores'][loser_role] = 0
                    LobbyConsumer.rooms[self.room_id]['game']['f']['scores'][winner_role] = 99
                    LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
                    await self.create_multi_game_records()
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'game_over',
                            'winner': winner,
                            'loser': loser,
                            'score': LobbyConsumer.rooms[self.room_id]['game']['f']['scores'],
                            'match': 'f',
                        }
                    )
                    return
                LobbyConsumer.rooms[self.room_id]['game']['f']['roles'] = {
                    'left' : LobbyConsumer.rooms[self.room_id]['game']['winner_a'],
                    'right' : LobbyConsumer.rooms[self.room_id]['game']['winner_b'],
                }
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'final_game_start',
                        'game': LobbyConsumer.rooms[self.room_id]['game']
                    }
                )
        elif data['type'] == 'start_final_game':
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'f':
                asyncio.create_task(self.start_ball_movement('f'))
        elif data['type'] == 'disconnect':
            await self.close()

    async def start_ball_movement(self, match):
        self.ball_count = 0
        self.past_ball_position = []
        while self.status == 'playing' and self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game'][match]['players']) == 2:
            self.update_ball_position(match)
            self.ball_count += 1
            self.past_ball_position.append(self.game[match]['ball'].copy())
            if len(self.past_ball_position) > 33:
                self.past_ball_position.pop(0)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'update_game',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            await asyncio.sleep(0.03)

    def update_ball_position(self, match):
        self.match = self.game[match]      
        self.match['player_bar']['left'] = max(0, min(720, self.match['player_bar']['left'] + self.match['bar_move']['left']))
        self.match['player_bar']['right'] = max(0, min(720, self.match['player_bar']['right'] + self.match['bar_move']['right']))
        if -19 < self.match['ball']['speedX'] < 19  and -39 < self.match['ball']['speedY'] < 39:
            self.match['ball']['speedX'] *= 1.02
            self.match['ball']['speedY'] *= 1.02
        self.match['ball']['x'] += self.match['ball']['speedX']
        self.match['ball']['y'] += self.match['ball']['speedY']
        # 위 야래 벽에 부딪히면 방향 바꾸기
        if self.match['ball']['y'] + self.match['ball']['radius'] > 900 or self.match['ball']['y'] - self.match['ball']['radius'] < 0:
            self.match['ball']['speedY'] = -self.match['ball']['speedY']
            
        if self.match['ball']['y'] + self.match['ball']['radius'] > 900:
            self.match['ball']['y'] = 900 - self.match['ball']['radius']
        elif self.match['ball']['y'] - self.match['ball']['radius'] < 0:
            self.match['ball']['y'] = self.match['ball']['radius']
        # 왼쪽 player bar에 부딪히면 방향 바꾸기
        if 20 < self.match['ball']['x'] - self.match['ball']['radius'] < 40:
            if self.match['ball']['y'] > self.match['player_bar']['left'] and self.match['ball']['y'] < self.match['player_bar']['left'] + 180:
                degree = (self.match['player_bar']['left'] + 90 - self.match['ball']['y']) * 8 / 9
                self.match['ball']['speedY'] = math.tan(math.radians(-degree)) * 5
                self.match['ball']['speedX'] = 5
        # 오른쪽 player bar에 부딪히면 방향 바꾸기
        if 1160 < self.match['ball']['x'] + self.match['ball']['radius'] < 1180:
            if self.match['ball']['y'] > self.match['player_bar']['right'] and self.match['ball']['y'] < self.match['player_bar']['right'] + 180:
                degree = (self.match['player_bar']['right'] + 90 - self.match['ball']['y']) * 8 / 9
                self.match['ball']['speedY'] = math.tan(math.radians(degree)) * (-5)
                self.match['ball']['speedX'] = -5
        # 왼쪽, 오른쪽 벽에 부딪히면 점수 올리기
        if (self.match['ball']['x'] - self.match['ball']['radius'] < 0) or (self.match['ball']['x'] + self.match['ball']['radius'] > 1200):
            if self.match['ball']['x'] - self.match['ball']['radius'] < 0:
                self.match['scores']['right'] += 1
                self.record_goal('right', match)
            else:
                self.match['scores']['left'] += 1
                self.record_goal('left', match)
            asyncio.create_task(self.broadcast_scores())
            asyncio.create_task(self.check_game_over(match))
            self.reset_ball(match)

    def record_goal(self, goal_user_position, match):
        match_player_1 = self.game[match]['players'][0]
        match_player_2 = self.game[match]['players'][1]
        goal_user_name = ''
        if self.game['roles'][match_player_1] == goal_user_position:
            goal_user_name = match_player_1
        else:
            goal_user_name = match_player_2
        self.game[match]['record'].append({
            'goal_user_name': goal_user_name,
            'goal_user_position': goal_user_position,
            'ball_start_position': self.past_ball_position[0].copy(),
            'ball_end_position': self.game[match]['ball'].copy(),
            'timestamp': self.ball_count
        })

    def reset_ball(self, match):
        self.game[match]['ball']['x'] = 600
        self.game[match]['ball']['y'] = 450
        self.game[match]['ball']['speedX'] = 10 * (1 if random.random() > 0.5 else -1)
        self.game[match]['ball']['speedY'] = 10 * (1 if random.random() > 0.5 else -1)

    async def broadcast_scores(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_game',
                'game': self.game,
            }
        )

    async def check_game_over(self, match):
        if self.game[match]['scores']['left'] >= 3:
            await self.game_end('left', 'right', match)
        elif self.game[match]['scores']['right'] >= 3:
            await self.game_end('right', 'left', match)

    async def game_end(self, winner, loser, match):
        player1 = self.game[match]['players'][0]
        player2 = self.game[match]['players'][1]
        winner_username = player1 if self.game['roles'][player1] == winner else player2
        loser_username = player1 if self.game['roles'][player1] == loser else player2

        LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].append(winner_username)
        await self.game_over_match(winner_username, loser_username, match)

    async def game_over_match(self, winner, loser, match):
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'] = []
        left_score = self.game[match]['scores']['left']
        right_score = self.game[match]['scores']['right']
        if (left_score > right_score):
            winner_score = left_score
            loser_score = right_score
        else:
            winner_score = right_score
            loser_score = left_score
        game_data = await get_game_data(winner, loser, winner_score, loser_score)
        game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=self.game[match]['record'])
        TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
        if match == 'a':
            LobbyConsumer.rooms[self.room_id]['game']['winner_a'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'left'
        elif match == 'b':
            LobbyConsumer.rooms[self.room_id]['game']['winner_b'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'right'
        elif match == 'f':
            LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
            await self.create_multi_game_records()
        LobbyConsumer.rooms[self.room_id]['game']['roles'][loser] = 'observer'
        LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        LobbyConsumer.rooms[self.room_id]['game']['match'][loser] = 'f'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_over',
                'winner': winner,
                'loser': loser,
                'score': self.game[match]['scores'],
                'match': match,
            }
        )


    async def update_room_list(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    def update_bar_position(self, direction, role, match):
        if direction == 'up':
            self.game[match]['bar_move'][role] = -20
        elif direction == 'down':
            self.game[match]['bar_move'][role] = 20

    async def game_start(self, event):
        match = event['game']['match'][self.scope['user'].username]
        role = event['game']['roles'][self.scope['user'].username]
        self.status = 'game_waiting'
        match_a_player = event['game']['a']['players']
        match_b_player = event['game']['b']['players'] 
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': event['game'][match]['roles'],
            'you': self.scope['user'].username,
            'match_a_player': match_a_player,
            'match_b_player': match_b_player,
        }))

    async def final_game_start(self, event):
        match = 'f'
        role = event['game']['roles'][self.scope['user'].username]
        roles = {
            LobbyConsumer.rooms[self.room_id]['game']['roles'][event['game'][match]['players'][0]] : event['game'][match]['players'][0],
            LobbyConsumer.rooms[self.room_id]['game']['roles'][event['game'][match]['players'][1]] : event['game'][match]['players'][1],
        } 
        await self.send(text_data=json.dumps({
            'type': 'final_game_start',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': roles,
        }))

    async def update_game(self, event):
        match = event['game']['match'][self.scope['user'].username]
        role = event['game']['roles'][self.scope['user'].username]
        await self.send(text_data=json.dumps({
            'type': 'update_game',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': event['game'][match]['roles'],
            'you': self.scope['user'].username,
        }))

    async def game_over(self, event):
        if event['winner'] == self.scope['user'].username or event['loser'] == self.scope['user'].username:
            self.status = 'game_waiting'
        if event['match'] == 'f':
            LobbyConsumer.rooms[self.room_id]['status'] = 'room'
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'loser': event['loser'],
            'score': event['score'],
            'match': event['match'],
            'you': self.scope['user'].username,
            'room_id': self.room_id,
        }))

    async def error(self, event):
        self.status = 'error'
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))

    async def create_multi_game_records(self):
        await sync_to_async(MultiGameRecord.objects.create)(
            game1=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][0]),
            game2=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][1]),
            game3=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][2]),
            player1=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][0]),
            player2=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][1]),
            player3=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][2]),
            player4=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][3]),
        )
        del TournamentGameConsumer.game_record_list[self.room_id]
        del TournamentGameConsumer.game_player_list[self.room_id]



class LocalGameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'anonymous user'
            }))
            await self.close()
            return
        self.host_username = self.scope['url_route']['kwargs']['host_username']
        self.check = False
        self.room_group_name = f"local_game_{self.host_username}"
        await self.accept()
        if self.host_username != self.scope['user'].username:
            self.check = True
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'You are not host',
            }))
            return
        self.game_status = 'waiting'
        self.game = {
            'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
            'player_bar': {'left': 360, 'right': 360},
            'roles': {'left': 'left', 'right': 'right'},
            'scores': {'left': 0, 'right': 0},
            'bar_move': {'left': 0, 'right': 0},
        }

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_start',
                'game': self.game
            }
        )

    async def disconnect(self, close_code):
        if self.scope['user'].is_anonymous:
            return
        if self.check == True:
            return
        del self.game
        self.game_status = 'game_over'
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            self.game_status = 'playing'
            asyncio.create_task(self.start_ball_movement())
        elif data['type'] == 'move_bar':
            self.update_bar_position(data['direction'], data['role'])

    async def start_ball_movement(self):
        while self.game_status == 'playing':
            self.update_ball_position()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'update_game',
                    'game': self.game
                }
            )
            await asyncio.sleep(0.03)

    def update_ball_position(self):
        self.game['player_bar']['left'] = max(0, min(720, self.game['player_bar']['left'] + self.game['bar_move']['left']))
        self.game['player_bar']['right'] = max(0, min(720, self.game['player_bar']['right'] + self.game['bar_move']['right']))
        if -19 < self.game['ball']['speedX'] < 19  and -39 < self.game['ball']['speedY'] < 39:
            self.game['ball']['speedX'] *= 1.02
            self.game['ball']['speedY'] *= 1.02
        self.game['ball']['x'] += self.game['ball']['speedX']
        self.game['ball']['y'] += self.game['ball']['speedY']

        # Bounce off top and bottom walls
        if self.game['ball']['y'] + self.game['ball']['radius'] > 900 or self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['speedY'] = -self.game['ball']['speedY']

        if self.game['ball']['y'] + self.game['ball']['radius'] > 900:
            self.game['ball']['y'] = 900 - self.game['ball']['radius']
        elif self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['y'] = 0 + self.game['ball']['radius']
        
        # Bounce off paddles
        if 20 < self.game['ball']['x'] - self.game['ball']['radius'] < 40:
            if self.game['ball']['y'] > self.game['player_bar']['left'] and self.game['ball']['y'] < self.game['player_bar']['left'] + 180:
                degree = (self.game['player_bar']['left'] + 90 - self.game['ball']['y']) * 8 / 9
                self.game['ball']['speedY'] = math.tan(math.radians(-degree)) * 5
                self.game['ball']['speedX'] = 5
        if 1160 < self.game['ball']['x'] + self.game['ball']['radius'] < 1180:
            if self.game['ball']['y'] > self.game['player_bar']['right'] and self.game['ball']['y'] < self.game['player_bar']['right'] + 180:
                degree = (self.game['player_bar']['right'] + 90 - self.game['ball']['y']) * 8 / 9
                self.game['ball']['speedY'] = math.tan(math.radians(degree)) * (-5)
                self.game['ball']['speedX'] = -5
        # Score points
        if self.game['ball']['x'] - self.game['ball']['radius'] < 0 or self.game['ball']['x'] + self.game['ball']['radius'] > 1200:
            if self.game['ball']['x'] - self.game['ball']['radius'] < 0:
                self.game['scores']['right'] += 1
            else:
                self.game['scores']['left'] += 1
            asyncio.create_task(self.broadcast_scores())
            asyncio.create_task(self.check_game_over())
            self.reset_ball()
    
    async def broadcast_scores(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_game',
                'game': self.game
            }
        )
    
    async def check_game_over(self):
        if self.game['scores']['left'] >= 3:
            await self.game_end('left', 'right')
        elif self.game['scores']['right'] >= 3:
            await self.game_end('right', 'left')
    
    async def game_end(self, winner, loser):
        self.game_status = 'game_over'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_over',
                'winner': winner,
                'loser': loser
            }
        )
        
    async def game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'loser': event['loser']
        }))

    def reset_ball(self):
        self.game['ball']['x'] = 600
        self.game['ball']['y'] = 450
        self.game['ball']['speedX'] = 10 * (1 if random.random() > 0.5 else -1)
        self.game['ball']['speedY'] = 10 * (1 if random.random() > 0.5 else -1)

    def update_bar_position(self, direction, role):
        if direction == 'up':
            self.game['bar_move'][role] = -20
        elif direction == 'down':
            self.game['bar_move'][role] = 20
        elif direction == 'stop':
            self.game['bar_move'][role] = 0
        

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'game': event['game']
        }))

    async def update_game(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update_game',
            'game': event['game']
        }))


class CustomGameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'anonymous user'
            }))
            await self.close()
            return
        self.room_id_str = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = self.room_id_str
        self.room_id = int(self.room_id_str)
        self.status = 'waiting'
        self.ball_count = 0
        self.past_ball_position = []

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        if self.room_id not in LobbyConsumer.rooms:
            await self.send_error_message('Room does not exist')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['status'] != 'game':
            await self.send_error_message('Room is not in game status')
            await self.close()
            return

        if self.scope['user'].username not in LobbyConsumer.rooms[self.room_id]['in_game_players']:
            await self.send_error_message('You are not in game')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['mode'] != 'matchmaking' and \
            LobbyConsumer.rooms[self.room_id]['mode'] != 2:
            await self.send_error_message('Room is not in matchmaking mode')
            await self.close()
            return

        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            LobbyConsumer.rooms[self.room_id]['game'] = {
                'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                'player_bar': {'left': 360, 'right': 360},
                'scores': {'left': 0, 'right': 0},
                'players': [],
                'roles': {},
                'bar_move': {'left': 0, 'right': 0},
                'record': [],
                'items': [],
                'bar_size' : {'left': 5, 'right': 5},
            }
            
        LobbyConsumer.rooms[self.room_id]['game']['players'].append(self.scope['user'].username)
        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 2:
            LobbyConsumer.rooms[self.room_id]['game']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['in_game_players'][0],
                'right': LobbyConsumer.rooms[self.room_id]['in_game_players'][1],
            }
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            LobbyConsumer.rooms[self.room_id]['status'] = 'playing'
        self.game = LobbyConsumer.rooms[self.room_id]['game']

    async def send_error_message(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
        self.status = 'connect error'

    async def disconnect(self, close_code):
        if self.scope['user'].is_anonymous:
            return
        if self.room_id not in LobbyConsumer.rooms:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'connect error':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        if self.status == 'playing' or self.status == 'waiting':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': 'user disconnected'
                }
            )
            LobbyConsumer.rooms[self.room_id]['game']['players'].remove(self.scope['user'].username)
            # 부전승 나는 경우 => 한 명이 일방적으로 나감
            if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 1:
                winner_name = LobbyConsumer.rooms[self.room_id]['game']['players'][0]
                loser_name = self.scope['user'].username
                game_data = await get_game_data(winner_name, loser_name, 99, 0)
                await create_game_records(game_data, is_tournament=False, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['record'])
            elif len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 0:
                del LobbyConsumer.rooms[self.room_id]
            await self.update_room_list()

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            if self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game']['players']) != 2:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'error',
                        'message': 'Not enough players'
                    }
                )
                return
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and self.scope['user'].username == LobbyConsumer.rooms[self.room_id]['game']['roles']['left']:
                asyncio.create_task(self.start_ball_movement())
        elif data['type'] == 'move_bar':
            self.update_bar_position(data['direction'], data['role'])
        elif data['type'] == 'stop_bar':
            self.game['bar_move'][data['role']] = 0

    async def start_ball_movement(self):
        while self.status == 'playing' and self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 2:
            self.update_ball_position()
            self.ball_count += 1
            self.past_ball_position.append(self.game['ball'].copy()) 
            if len(self.past_ball_position) > 33:
                self.past_ball_position.pop(0)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'update_game',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            await asyncio.sleep(0.03)

    def update_ball_position(self):
        left_bar_size = 0
        right_bar_size = 0
        if self.game['bar_size']['left'] == 5:
            left_bar_size = 180
        elif self.game['bar_size']['left'] == 2.5:
            left_bar_size = 360
        elif self.game['bar_size']['left'] == 10:
            left_bar_size = 90
        if self.game['bar_size']['right'] == 5:
            right_bar_size = 180
        elif self.game['bar_size']['right'] == 2.5:
            right_bar_size = 360
        elif self.game['bar_size']['right'] == 10:
            right_bar_size = 90
        
        self.game['player_bar']['left'] = max(0, min(900 - left_bar_size, self.game['player_bar']['left'] + self.game['bar_move']['left']))
        self.game['player_bar']['right'] = max(0, min(900 - right_bar_size, self.game['player_bar']['right'] + self.game['bar_move']['right']))
        if -19 < self.game['ball']['speedX'] < 19 and -39 < self.game['ball']['speedY'] < 39:
            self.game['ball']['speedX'] *= 1.02
            self.game['ball']['speedY'] *= 1.02
        if len(LobbyConsumer.rooms[self.room_id]['items']) >= 1:
            self.create_item()
            self.apply_item()
            self.move_item()
        self.game['ball']['x'] += self.game['ball']['speedX']
        self.game['ball']['y'] += self.game['ball']['speedY']
        # 위 야래 벽에 부딪히면 방향 바꾸기
        if self.game['ball']['y'] + self.game['ball']['radius'] > 900 or self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['speedY'] = -self.game['ball']['speedY']
        
        if self.game['ball']['y'] + self.game['ball']['radius'] > 900:
            self.game['ball']['y'] = 900 - self.game['ball']['radius']
        elif self.game['ball']['y'] - self.game['ball']['radius'] < 0:
            self.game['ball']['y'] = self.game['ball']['radius']
        
        # 왼쪽 player bar에 부딪히면 방향 바꾸기
        if 20 < self.game['ball']['x'] - self.game['ball']['radius'] < 40:
            if self.game['ball']['y'] > self.game['player_bar']['left'] and self.game['ball']['y'] < self.game['player_bar']['left'] + (900 / self.game['bar_size']['left']):
                degree = (self.game['player_bar']['left'] + (900 / self.game['bar_size']['left'] / 2) - self.game['ball']['y']) * 8 / 9
                if degree < -80 or degree > 80:
                    degree = 80 if degree > 80 else -80
                self.game['ball']['speedY'] = math.tan(math.radians(-degree)) * 5
                self.game['ball']['speedX'] = 5
        # 오른쪽 player bar에 부딪히면 방향 바꾸기
        if 1160 < self.game['ball']['x'] + self.game['ball']['radius'] < 1180:
            if self.game['ball']['y'] > self.game['player_bar']['right'] and self.game['ball']['y'] < self.game['player_bar']['right'] + (900 / self.game['bar_size']['right']):
                degree = (self.game['player_bar']['right'] + (900 / self.game['bar_size']['left'] / 2) - self.game['ball']['y']) * 8 / 9
                if degree < -80 or degree > 80:
                    degree = 80 if degree > 80 else -80
                self.game['ball']['speedY'] = math.tan(math.radians(degree)) * (-5)
                self.game['ball']['speedX'] = -5
        # 왼쪽, 오른쪽 벽에 부딪히면 점수 올리기
        if (self.game['ball']['x'] - self.game['ball']['radius'] < 0) or (self.game['ball']['x'] + self.game['ball']['radius'] > 1200):
            if self.game['ball']['x'] - self.game['ball']['radius'] < 0:
                self.game['scores']['right'] += 1
                self.record_goal('right')
            else:
                self.game['scores']['left'] += 1
                self.record_goal('left')
            asyncio.create_task(self.broadcast_scores())
            asyncio.create_task(self.check_game_over())
            self.reset_ball()
            
            
    def create_item(self):
        if len(self.game['items']) < 6:
            x = random.randint(200, 1000)
            y = 0
            item_type = random.choice(LobbyConsumer.rooms[self.room_id]['items'])
            self.game['items'].append({'x': x, 'y': y, 'type': item_type})
        
    def move_item(self):
        for item in self.game['items']:
            item['y'] += 20
            if item['y'] > 900:
                self.game['items'].remove(item)
    
    def apply_item(self):
        for item in LobbyConsumer.rooms[self.room_id]['game']['items']:
            if item['x'] - 50 < self.game['ball']['x'] < item['x'] + 50 and item['y'] - 50 < self.game['ball']['y'] < item['y'] + 50:
                if item['type'] == 'speed_up':
                    if self.game['ball']['speedX'] > 0:
                        self.game['ball']['speedY'] = 19 / (self.game['ball']['speedX'] / self.game['ball']['speedY'])
                        self.game['ball']['speedX'] = 19
                    else:
                        self.game['ball']['speedY'] = -19 / (self.game['ball']['speedX'] / self.game['ball']['speedY'])
                        self.game['ball']['speedX'] = -19
                elif item['type'] == 'speed_down':
                    self.game['ball']['speedX'] *= 0.1
                    self.game['ball']['speedY'] *= 0.1
                elif item['type'] == 'bar_up':
                    if self.game['ball']['speedX'] > 0:
                        self.game['bar_size']['left'] = 2.5
                    else:
                        self.game['bar_size']['right'] = 2.5
                elif item['type'] == 'bar_down':
                    if self.game['ball']['speedX'] > 0:
                        self.game['bar_size']['left'] = 10
                    else:
                        self.game['bar_size']['right'] = 10
                    
                LobbyConsumer.rooms[self.room_id]['game']['items'].remove(item)
            

    def record_goal(self, goal_user_position):
        self.game['record'].append({
            'goal_user_name': self.game['roles'][goal_user_position],
            'goal_user_position': goal_user_position,
            'ball_start_position': self.past_ball_position[0].copy(),
            'ball_end_position': self.game['ball'].copy(),
            'timestamp': self.ball_count
        })

    def reset_ball(self):
        self.game['ball']['x'] = 600
        self.game['ball']['y'] = 450
        self.game['ball']['speedX'] = 10 * (1 if random.random() > 0.5 else -1)
        self.game['ball']['speedY'] = 10 * (1 if random.random() > 0.5 else -1)

    async def broadcast_scores(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_game',
                'game': self.game,
            }
        )

    async def check_game_over(self):
        if self.game['scores']['left'] >= LobbyConsumer.rooms[self.room_id]['goal_score']:
            await self.game_end('left', 'right')
        elif self.game['scores']['right'] >= LobbyConsumer.rooms[self.room_id]['goal_score']:
            await self.game_end('right', 'left')

    async def game_end(self, winner, loser):
        self.status = 'game_over'
        LobbyConsumer.rooms[self.room_id]['status'] = 'room'
        LobbyConsumer.rooms[self.room_id]['in_game_players'] = []
        winner_username = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
        loser_username = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
        winner_score = self.game['scores'][winner]
        loser_score = self.game['scores'][loser]
        game_data = await get_game_data(winner_username, loser_username, winner_score, loser_score)
        await create_game_records(game_data, is_tournament=False, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['record'])
        del LobbyConsumer.rooms[self.room_id]['game']
        if LobbyConsumer.rooms[self.room_id]['mode'] == 'matchmaking':
            del LobbyConsumer.rooms[self.room_id]
        
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_over',
                'winner': winner_username,
                'loser': loser_username,
            }
        )
        await self.update_room_list()

    async def update_room_list(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    def update_bar_position(self, direction, role):
        if direction == 'up':
            self.game['bar_move'][role] = -20
        elif direction == 'down':
            self.game['bar_move'][role] = 20

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'game': event['game'],
            'you': 'left' if self.scope['user'].username == event['game']['roles']['left'] else 'right'
        }))

    async def update_game(self, event):
        await self.send(text_data=json.dumps({
            'type': 'update_game',
            'game': event['game'],
            'you': 'left' if self.scope['user'].username == event['game']['roles']['left'] else 'right'
        }))

    async def game_over(self, event):
        self.status = 'game_over'
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'loser': event['loser'],
            'room_id': self.room_id
        }))

    async def error(self, event):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))
        
        
        

class CustomTournamentGameConsumer(AsyncWebsocketConsumer):
    game_record_list = {}
    game_player_list = {}
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.accept()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'anonymous user'
            }))
            await self.close()
            return
        self.room_id_str = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = self.room_id_str
        self.room_id = int(self.room_id_str)
        self.status = 'waiting'
        self.ball_count = 0
        self.past_ball_position = []
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        if self.room_id not in LobbyConsumer.rooms:
            await self.send_error_message('Room does not exist')
            await self.close()
            return

        if LobbyConsumer.rooms[self.room_id]['status'] != 'game':
            await self.send_error_message('Room is not in game status')
            await self.close()
            return

        if self.scope['user'].username not in LobbyConsumer.rooms[self.room_id]['in_game_players']:
            await self.send_error_message('You are not in game')
            await self.close()
            return
        LobbyConsumer.rooms[self.room_id]['in_game_players'].remove(self.scope['user'].username)
        if LobbyConsumer.rooms[self.room_id]['mode'] != 4:
            await self.send_error_message('Room is not in tournament mode')
            await self.close()
            return
        if self.room_id not in TournamentGameConsumer.game_record_list:
            TournamentGameConsumer.game_record_list[self.room_id] = []
            TournamentGameConsumer.game_player_list[self.room_id] = []
        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            LobbyConsumer.rooms[self.room_id]['game'] = {
                'a' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'record' : [],
                    'items' : [],
                    'bar_size' : {'left': 5, 'right': 5},
                },
                'b' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'record': [],
                    'items' : [],
                    'bar_size' : {'left': 5, 'right': 5},
                },
                'f' : {
                    'ball': {'x': 600, 'y': 450, 'radius': 10, 'speedX': 10, 'speedY': 10},
                    'player_bar': {'left': 360, 'right': 360},
                    'scores': {'left': 0, 'right': 0},
                    'bar_move': {'left': 0, 'right': 0},
                    'roles' : {},
                    'players' : [],
                    'waiting_players' : [],
                    'record': [],
                    'items' : [],
                    'bar_size' : {'left': 5, 'right': 5},
                },
                'players': [],
                'roles' : {},
                'match' : {},
                'items' : [],
                'winner_a' : None,
                'winner_b' : None,
                'winner_f' : None,
            }

        LobbyConsumer.rooms[self.room_id]['game']['players'].append(self.scope['user'].username)
        TournamentGameConsumer.game_player_list[self.room_id].append(self.scope['user'].username)

        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 4:
            LobbyConsumer.rooms[self.room_id]['game']['roles'] = {
                LobbyConsumer.rooms[self.room_id]['game']['players'][0]: 'left',
                LobbyConsumer.rooms[self.room_id]['game']['players'][1]: 'right',
                LobbyConsumer.rooms[self.room_id]['game']['players'][2]: 'left',
                LobbyConsumer.rooms[self.room_id]['game']['players'][3]: 'right',
            }
            LobbyConsumer.rooms[self.room_id]['game']['match'] = {
                LobbyConsumer.rooms[self.room_id]['game']['players'][0]: 'a',
                LobbyConsumer.rooms[self.room_id]['game']['players'][1]: 'a',
                LobbyConsumer.rooms[self.room_id]['game']['players'][2]: 'b',
                LobbyConsumer.rooms[self.room_id]['game']['players'][3]: 'b',
            }
            LobbyConsumer.rooms[self.room_id]['game']['a']['players'] = [LobbyConsumer.rooms[self.room_id]['game']['players'][0], LobbyConsumer.rooms[self.room_id]['game']['players'][1]]
            LobbyConsumer.rooms[self.room_id]['game']['b']['players'] = [LobbyConsumer.rooms[self.room_id]['game']['players'][2], LobbyConsumer.rooms[self.room_id]['game']['players'][3]]
            LobbyConsumer.rooms[self.room_id]['game']['a']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['game']['players'][0],
                'right': LobbyConsumer.rooms[self.room_id]['game']['players'][1],
            }
            LobbyConsumer.rooms[self.room_id]['game']['b']['roles'] = {
                'left': LobbyConsumer.rooms[self.room_id]['game']['players'][2],
                'right': LobbyConsumer.rooms[self.room_id]['game']['players'][3],
            }
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            LobbyConsumer.rooms[self.room_id]['status'] = 'playing'
        self.game = LobbyConsumer.rooms[self.room_id]['game']
        await self.update_room_list()

    async def send_error_message(self, message):
        self.status = 'connect error'
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    async def disconnect(self, close_code):

        if self.scope['user'].is_anonymous:
            return
        if self.room_id not in LobbyConsumer.rooms:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        if 'game' not in LobbyConsumer.rooms[self.room_id]:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'connect error':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.status == 'waiting':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'error',
                    'message': 'user disconnected'
                }
            )

        if LobbyConsumer.rooms[self.room_id]['status'] == 'room':
            del LobbyConsumer.rooms[self.room_id]['game']
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if self.scope['user'].username in LobbyConsumer.rooms[self.room_id]['game']['players']:
            LobbyConsumer.rooms[self.room_id]['game']['players'].remove(self.scope['user'].username)

        if self.status == 'error':
            del LobbyConsumer.rooms[self.room_id]
            await self.update_room_list()
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        if len(LobbyConsumer.rooms[self.room_id]['game']['players']) == 0:
            del LobbyConsumer.rooms[self.room_id]['game']
            await self.update_room_list()
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return


        match = LobbyConsumer.rooms[self.room_id]['game']['match'][self.scope['user'].username]
        role = LobbyConsumer.rooms[self.room_id]['game']['roles'][self.scope['user'].username]

        if role == 'observer':
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            return

        # final 유저가 대기중에 나가는 경우 ex) a매치는 진행중인데 b매치의 승자가 나가는 경우
        if match == 'f':
            if self.scope['user'].username in LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']:
                LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].remove(self.scope['user'].username)
                if len(LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']) == 0:
                    await self.channel_layer.group_discard(
                        self.room_group_name,
                        self.channel_name
                    )
                    return

        # a, b, f매치중 나가는 경우 부전 패 처리
        await self.handle_walkover(match)

        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 부전 패 처리
    async def handle_walkover(self, match):
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'].remove(self.scope['user'].username)
        winner = LobbyConsumer.rooms[self.room_id]['game'][match]['players'][0]
        if match != 'f':
            LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].append(winner)
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'] = []
        loser = self.scope['user'].username
        winner_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
        loser_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
        game_data = await get_game_data(winner, loser, 99, 0)
        game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=LobbyConsumer.rooms[self.room_id]['game'][match]['record'])
        TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
        LobbyConsumer.rooms[self.room_id]['game'][match]['scores'][loser_role] = 0
        LobbyConsumer.rooms[self.room_id]['game'][match]['scores'][winner_role] = 99
        if match == 'a':
            LobbyConsumer.rooms[self.room_id]['game']['winner_a'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'left'
            LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        elif match == 'b':
            LobbyConsumer.rooms[self.room_id]['game']['winner_b'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'right'
            LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        elif match == 'f':
            LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
            await self.create_multi_game_records()
        await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'winner': winner,
                    'loser': loser,
                    'score': LobbyConsumer.rooms[self.room_id]['game'][match]['scores'],
                    'match': match,
                }
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data['type'] == 'start_game':
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'a':
                asyncio.create_task(self.start_ball_movement('a'))
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'b':
                asyncio.create_task(self.start_ball_movement('b'))
        elif data['type'] == 'move_bar':
            self.update_bar_position(data['direction'], data['role'], data['match'])
        elif data['type'] == 'stop_bar':
            self.game[data['match']]['bar_move'][data['role']] = 0
        elif data['type'] == 'final_ready':
            if self.scope['user'].username == self.game['winner_a'] or self.scope['user'].username == self.game['winner_b']:
                LobbyConsumer.rooms[self.room_id]['game']['f']['players'].append(self.scope['user'].username)
            if len(LobbyConsumer.rooms[self.room_id]['game']['f']['players']) == 2:
                if len(LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players']) != 2:
                    # 이때가 f 매치 부전승 처리
                    winner = self.scope['user'].username
                    loser = LobbyConsumer.rooms[self.room_id]['game']['f']['players'][0]
                    game_data = await get_game_data(winner, loser, 99, 0)
                    game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=LobbyConsumer.rooms[self.room_id]['game']['f']['record'])
                    TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
                    winner_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][winner]
                    loser_role = LobbyConsumer.rooms[self.room_id]['game']['roles'][loser]
                    LobbyConsumer.rooms[self.room_id]['game']['f']['scores'][loser_role] = 0
                    LobbyConsumer.rooms[self.room_id]['game']['f']['scores'][winner_role] = 99
                    LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
                    await self.create_multi_game_records()
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'game_over',
                            'winner': winner,
                            'loser': loser,
                            'score': LobbyConsumer.rooms[self.room_id]['game']['f']['scores'],
                            'match': 'f',
                        }
                    )
                    return
                LobbyConsumer.rooms[self.room_id]['game']['f']['roles'] = {
                    'left' : LobbyConsumer.rooms[self.room_id]['game']['winner_a'],
                    'right' : LobbyConsumer.rooms[self.room_id]['game']['winner_b'],
                }
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'final_game_start',
                        'game': LobbyConsumer.rooms[self.room_id]['game']
                    }
                )
        elif data['type'] == 'start_final_game':
            self.status = 'playing'
            if self.room_id in LobbyConsumer.rooms and data['role'] == 'left' and data['match'] == 'f':
                asyncio.create_task(self.start_ball_movement('f'))
        elif data['type'] == 'disconnect':
            await self.close()

    async def start_ball_movement(self, match):
        self.ball_count = 0
        self.past_ball_position = []
        while self.status == 'playing' and self.room_id in LobbyConsumer.rooms and len(LobbyConsumer.rooms[self.room_id]['game'][match]['players']) == 2:
            self.update_ball_position(match)
            self.ball_count += 1
            self.past_ball_position.append(self.game[match]['ball'].copy())
            if len(self.past_ball_position) > 33:
                self.past_ball_position.pop(0)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'update_game',
                    'game': LobbyConsumer.rooms[self.room_id]['game']
                }
            )
            await asyncio.sleep(0.03)

    def update_ball_position(self, match):
        self.match = self.game[match]
        left_bar_size = 0
        right_bar_size = 0
        if self.match['bar_size']['left'] == 5:
            left_bar_size = 180
        elif self.match['bar_size']['left'] == 2.5:
            left_bar_size = 360
        elif self.match['bar_size']['left'] == 10:
            left_bar_size = 90
        if self.match['bar_size']['right'] == 5:
            right_bar_size = 180
        elif self.match['bar_size']['right'] == 2.5:
            right_bar_size = 360
        elif self.match['bar_size']['right'] == 10:
            right_bar_size = 90
        self.match['player_bar']['left'] = max(0, min(900 - left_bar_size, self.match['player_bar']['left'] + self.match['bar_move']['left']))
        self.match['player_bar']['right'] = max(0, min(900 - right_bar_size, self.match['player_bar']['right'] + self.match['bar_move']['right']))
        if -19 < self.match['ball']['speedX'] < 19  and -39 < self.match['ball']['speedY'] < 39:
            self.match['ball']['speedX'] *= 1.02
            self.match['ball']['speedY'] *= 1.02
        self.match['ball']['x'] += self.match['ball']['speedX']
        self.match['ball']['y'] += self.match['ball']['speedY']
        
        if len(LobbyConsumer.rooms[self.room_id]['items']) >= 1:
            self.creat_item(match)
            self.apply_item(match)
            self.move_item(match)
        # 위 야래 벽에 부딪히면 방향 바꾸기
        if self.match['ball']['y'] + self.match['ball']['radius'] > 900 or self.match['ball']['y'] - self.match['ball']['radius'] < 0:
            self.match['ball']['speedY'] = -self.match['ball']['speedY']
        if self.match['ball']['y'] + self.match['ball']['radius'] > 900:
            self.match['ball']['y'] = 900 - self.match['ball']['radius']
        elif self.match['ball']['y'] - self.match['ball']['radius'] < 0:
            self.match['ball']['y'] = self.match['ball']['radius']
        # 왼쪽 player bar에 부딪히면 방향 바꾸기
        if 20 < self.match['ball']['x'] - self.match['ball']['radius'] < 40:
            if self.match['ball']['y'] > self.match['player_bar']['left'] and self.match['ball']['y'] < self.match['player_bar']['left'] + (900 / self.match['bar_size']['left']):
                degree = (self.match['player_bar']['left'] + 90 - self.match['ball']['y']) * 8 / 9
                self.match['ball']['speedY'] = math.tan(math.radians(-degree)) * 5
                self.match['ball']['speedX'] = 5
        # 오른쪽 player bar에 부딪히면 방향 바꾸기
        if 1160 < self.match['ball']['x'] + self.match['ball']['radius'] < 1180:
            if self.match['ball']['y'] > self.match['player_bar']['right'] and self.match['ball']['y'] < self.match['player_bar']['right'] + (900 / self.match['bar_size']['right']):
                degree = (self.match['player_bar']['right'] + 90 - self.match['ball']['y']) * 8 / 9
                self.match['ball']['speedY'] = math.tan(math.radians(degree)) * (-5)
                self.match['ball']['speedX'] = -5
        # 왼쪽, 오른쪽 벽에 부딪히면 점수 올리기
        if (self.match['ball']['x'] - self.match['ball']['radius'] < 0) or (self.match['ball']['x'] + self.match['ball']['radius'] > 1200):
            if self.match['ball']['x'] - self.match['ball']['radius'] < 0:
                self.match['scores']['right'] += 1
                self.record_goal('right', match)
            else:
                self.match['scores']['left'] += 1
                self.record_goal('left', match)
            asyncio.create_task(self.broadcast_scores())
            asyncio.create_task(self.check_game_over(match))
            self.reset_ball(match)


    def creat_item(self, match):
        if len(self.game[match]['items']) < 6:
            x = random.randint(200, 1000)
            y = 0
            item_type = random.choice(LobbyConsumer.rooms[self.room_id]['items'])
            LobbyConsumer.rooms[self.room_id]['game'][match]['items'].append({'x': x, 'y': y, 'type': item_type})

    def move_item(self, match):
        for item in self.game[match]['items']:
            item['y'] += 20
            if item['y'] > 900:
                self.game[match]['items'].remove(item)
    
    def apply_item(self, match):
        for item in self.game[match]['items']:
            if item['x'] - 50 < self.game[match]['ball']['x'] < item['x'] + 50 and item['y'] - 50 < self.game[match]['ball']['y'] < item['y'] + 50:
                if item['type'] == 'speed_up':
                    if self.game[match]['ball']['speedX'] > 0:
                        self.game[match]['ball']['speedY'] = 19 / (self.game[match]['ball']['speedX'] / self.game[match]['ball']['speedY'])
                        self.game[match]['ball']['speedX'] = 19
                    else:
                        self.game[match]['ball']['speedY'] = -19 / (self.game[match]['ball']['speedX'] / self.game[match]['ball']['speedY'])
                        self.game[match]['ball']['speedX'] = -19
                elif item['type'] == 'speed_down':
                    self.game[match]['ball']['speedX'] *= 0.1
                    self.game[match]['ball']['speedY'] *= 0.1
                elif item['type'] == 'bar_up':
                    if self.game[match]['ball']['speedX'] > 0:
                        self.game[match]['bar_size']['left'] = 2.5
                    else:
                        self.game[match]['bar_size']['right'] = 2.5
                elif item['type'] == 'bar_down':
                    if self.game[match]['ball']['speedX'] > 0:
                        self.game[match]['bar_size']['left'] = 10
                    else:
                        self.game[match]['bar_size']['right'] = 10
                self.game[match]['items'].remove(item)

    def record_goal(self, goal_user_position, match):
        match_player_1 = self.game[match]['players'][0]
        match_player_2 = self.game[match]['players'][1]
        goal_user_name = ''
        if self.game['roles'][match_player_1] == goal_user_position:
            goal_user_name = match_player_1
        else:
            goal_user_name = match_player_2
        self.game[match]['record'].append({
            'goal_user_name': goal_user_name,
            'goal_user_position': goal_user_position,
            'ball_start_position': self.past_ball_position[0].copy(),
            'ball_end_position': self.game[match]['ball'].copy(),
            'timestamp': self.ball_count
        })

    def reset_ball(self, match):
        self.game[match]['ball']['x'] = 600
        self.game[match]['ball']['y'] = 450
        self.game[match]['ball']['speedX'] = 10 * (1 if random.random() > 0.5 else -1)
        self.game[match]['ball']['speedY'] = 10 * (1 if random.random() > 0.5 else -1)

    async def broadcast_scores(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'update_game',
                'game': self.game,
            }
        )

    async def check_game_over(self, match):
        if self.game[match]['scores']['left'] >= LobbyConsumer.rooms[self.room_id]['goal_score']:
            await self.game_end('left', 'right', match)
        elif self.game[match]['scores']['right'] >= LobbyConsumer.rooms[self.room_id]['goal_score']:
            await self.game_end('right', 'left', match)

    async def game_end(self, winner, loser, match):
        player1 = self.game[match]['players'][0]
        player2 = self.game[match]['players'][1]
        winner_username = player1 if self.game['roles'][player1] == winner else player2
        loser_username = player1 if self.game['roles'][player1] == loser else player2

        LobbyConsumer.rooms[self.room_id]['game']['f']['waiting_players'].append(winner_username)
        await self.game_over_match(winner_username, loser_username, match)

    async def game_over_match(self, winner, loser, match):
        LobbyConsumer.rooms[self.room_id]['game'][match]['players'] = []
        left_score = self.game[match]['scores']['left']
        right_score = self.game[match]['scores']['right']
        if (left_score > right_score):
            winner_score = left_score
            loser_score = right_score
        else:
            winner_score = right_score
            loser_score = left_score
        game_data = await get_game_data(winner, loser, winner_score, loser_score)
        game_record_id = await create_game_records(game_data, is_tournament=True, game_record_details=self.game[match]['record'])
        TournamentGameConsumer.game_record_list[self.room_id].append(game_record_id)
        if match == 'a':
            LobbyConsumer.rooms[self.room_id]['game']['winner_a'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'left'
        elif match == 'b':
            LobbyConsumer.rooms[self.room_id]['game']['winner_b'] = winner
            LobbyConsumer.rooms[self.room_id]['game']['roles'][winner] = 'right'
        elif match == 'f':
            LobbyConsumer.rooms[self.room_id]['game']['winner_f'] = winner
            await self.create_multi_game_records()
        LobbyConsumer.rooms[self.room_id]['game']['roles'][loser] = 'observer'
        LobbyConsumer.rooms[self.room_id]['game']['match'][winner] = 'f'
        LobbyConsumer.rooms[self.room_id]['game']['match'][loser] = 'f'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_over',
                'winner': winner,
                'loser': loser,
                'score': self.game[match]['scores'],
                'match': match,
            }
        )


    async def update_room_list(self):
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "lobby",
            {
                'type': 'room_list_update',
                'rooms': list(LobbyConsumer.rooms.values())
            }
        )

    def update_bar_position(self, direction, role, match):
        if direction == 'up':
            self.game[match]['bar_move'][role] = -20
        elif direction == 'down':
            self.game[match]['bar_move'][role] = 20

    async def game_start(self, event):
        match = event['game']['match'][self.scope['user'].username]
        role = event['game']['roles'][self.scope['user'].username]
        self.status = 'game_waiting'
        match_a_player = event['game']['a']['players']
        match_b_player = event['game']['b']['players'] 
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': event['game'][match]['roles'],
            'you': self.scope['user'].username,
            'match_a_player': match_a_player,
            'match_b_player': match_b_player,
        }))

    async def final_game_start(self, event):
        match = 'f'
        role = event['game']['roles'][self.scope['user'].username]
        roles = {
            LobbyConsumer.rooms[self.room_id]['game']['roles'][event['game'][match]['players'][0]] : event['game'][match]['players'][0],
            LobbyConsumer.rooms[self.room_id]['game']['roles'][event['game'][match]['players'][1]] : event['game'][match]['players'][1],
        } 
        await self.send(text_data=json.dumps({
            'type': 'final_game_start',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': roles,
        }))

    async def update_game(self, event):
        match = event['game']['match'][self.scope['user'].username]
        role = event['game']['roles'][self.scope['user'].username]
        await self.send(text_data=json.dumps({
            'type': 'update_game',
            'game': event['game'][match],
            'role': role,
            'match': match,
            'roles': event['game'][match]['roles'],
            'you': self.scope['user'].username,
        }))

    async def game_over(self, event):
        if event['winner'] == self.scope['user'].username or event['loser'] == self.scope['user'].username:
            self.status = 'game_waiting'
        if event['match'] == 'f':
            LobbyConsumer.rooms[self.room_id]['status'] = 'room'
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'loser': event['loser'],
            'score': event['score'],
            'match': event['match'],
            'you': self.scope['user'].username,
            'room_id': self.room_id,
        }))

    async def error(self, event):
        self.status = 'error'
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': event['message']
        }))

    async def create_multi_game_records(self):
        await sync_to_async(MultiGameRecord.objects.create)(
            game1=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][0]),
            game2=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][1]),
            game3=await sync_to_async(SingleGameRecord.objects.get)(id=TournamentGameConsumer.game_record_list[self.room_id][2]),
            player1=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][0]),
            player2=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][1]),
            player3=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][2]),
            player4=await sync_to_async(CustomUser.objects.get)(username=TournamentGameConsumer.game_player_list[self.room_id][3]),
        )
        del TournamentGameConsumer.game_record_list[self.room_id]
        del TournamentGameConsumer.game_player_list[self.room_id]