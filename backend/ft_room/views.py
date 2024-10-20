from django.shortcuts import render

# Create your views here.
def room(request, room_id):
	return render(request, 'room.html', {"room_id": room_id})