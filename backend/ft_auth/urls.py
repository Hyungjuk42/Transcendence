from django.contrib import admin
from django.urls import path, include
from .views import oauth, Callback, refresh, OTPView, Callback

urlpatterns = [
	path('login/', oauth, name='login'),
	path('otp/', OTPView.as_view(), name='otp'),
	path('refresh/', refresh, name='refresh'),
	path('callback/', Callback.as_view(), name='callback'),
]
