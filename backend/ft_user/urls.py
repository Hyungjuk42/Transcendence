from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from .views import OtpUpdateView, FollowView, ProfileImageView, logout, SingleGameRecordListView, FollowDetailView, \
	MultiGameRecordListView, UserMeView, UserNameDetailView, SingleGameDetailListView, DayStatAPIView, RecentOpponentsAPIView, \
		AverageLineAPIView

urlpatterns = [
	path('otp/', OtpUpdateView.as_view(), name='otp_update'),
	path('me/', UserMeView.as_view(), name='me'),
	path('follow/', FollowView.as_view(), name='follow'),
	path('follow/<str:username>/', FollowDetailView.as_view(), name='follow_detail'),
	path('logout/', logout, name='logout'),
	path('game-detail/<int:game_id>/', SingleGameDetailListView.as_view(), name='single_game_record_detail'),
	path('<str:username>/record/single/', SingleGameRecordListView.as_view(), name='single_game_record'),
	path('<str:username>/record/multi/', MultiGameRecordListView.as_view(), name='multi_game_record'),
	path('<str:username>/user-day-stat/', DayStatAPIView.as_view(), name='user_stat'),
	path('<str:username>/user-recent-opponent/', RecentOpponentsAPIView.as_view(), name='user_recent_opponent'),
	path('<str:username>/', UserNameDetailView.as_view(), name='user_detail_by_username'),
	path('<str:username>/average-line/',AverageLineAPIView.as_view(), name='average_line'),
]
