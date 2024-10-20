from django.urls import path
from .views import *

# Create your views here.
urlpatterns = [
    path('', lobby, name='lobby'),
]