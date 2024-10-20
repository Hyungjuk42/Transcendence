from rest_framework.views import APIView
from .serializers import CreateGameRoomSerializer
from rest_framework.response import Response

class CreateGameRoomView(APIView):
	def post(self, request, format=None):
		serializer = CreateGameRoomSerializer(data=request.data)
		if serializer.is_valid():
			room_data_json = serializer.save()
			return Response(room_data_json, status=201)
		return Response(serializer.errors, status=400)

