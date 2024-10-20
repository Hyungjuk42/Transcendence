from django.urls import path, re_path
from .views import *

urlpatterns = [
    re_path(r'^(?P<room_id>\d+)/$', room, name='room'),
]
