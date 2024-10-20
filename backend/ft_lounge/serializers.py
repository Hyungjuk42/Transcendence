from rest_framework import serializers
from .manager import GameRoomManager
import json

class CreateGameRoomSerializer(serializers.Serializer):
	room_name = serializers.CharField(max_length=100)
	is_secret = serializers.BooleanField()
	mode = serializers.ChoiceField(choices=[('1v1', '1vs1'), ('tournament', 'Tournament')])
	password = serializers.CharField(max_length=100, required=False, allow_blank=True)

	def create(self, validated_data):
		room_name = validated_data['room_name']
		mode = validated_data['mode']
		password = validated_data.get('password', None)
		room_data_json = GameRoomManager.create_room(room_name, mode, password)
		
		return room_data_json
