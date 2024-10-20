from django.shortcuts import render

def game_room(request, room_number):
    return render(request, 'game_room.html', {"room_number": room_number})


def game(request, room_id):
	return render(request, 'game.html', {"room_id": room_id})

def tournament_game(request, room_id):
	return render(request, 'tournament_game.html', {"room_id": room_id})

def local_game(request, host_username):
	return render(request, 'local_game.html', {"host_username": host_username})