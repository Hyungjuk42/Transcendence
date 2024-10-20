from django.db import models
from django.contrib.auth.models import AbstractUser
from django_prometheus.models import ExportModelOperationsMixin
import os

def user_profile_image_path(instance, filename):
	# 파일이 업로드 될 경로: profile_images/<username>/<filename>
	return f'profile_images/{instance.username}/{filename}'

class CustomUser(ExportModelOperationsMixin("user"), AbstractUser):
	uid = models.IntegerField(primary_key=True)
	username = models.CharField(max_length=128, unique=True)
	otp_enabled = models.BooleanField(default=False, null=True)
	password = models.CharField(max_length=128, null=True, blank=True)
	refresh_token = models.CharField(max_length=4096, null=True, blank=True)
	win = models.IntegerField(default=0)
	lose = models.IntegerField(default=0)
	multi_nickname = models.CharField(max_length=128, null=True, blank=True)
	profile_image = models.ImageField(upload_to=user_profile_image_path, null=True, blank=True, max_length=4096)

	def __str__(self):
		return self.username
	def update_two_factor(self,otp_enabled):
		self.otp_enabled = otp_enabled
		self.save()
	def update_refresh_token(self, refresh_token):
		self.refresh_token = refresh_token
		self.save()

class FollowList(ExportModelOperationsMixin("follow_list"), models.Model):
	user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="follower_set", db_column="user")
	following_user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="following_set", db_column="following_user")

	def __str__(self):
		return f'{self.user} follows {self.following_user}'

	def save(self, *args, **kwargs):
		if self.user == self.following_user:
			raise Exception('자기 자신을 친구로 추가할 수 없습니다.')
		if FollowList.objects.filter(user=self.user, following_user=self.following_user).exists():
			raise Exception('이미 친구로 추가된 사용자입니다.')
		super().save(*args, **kwargs)

class SingleGameRecord(ExportModelOperationsMixin("game_record"), models.Model):
	id = models.BigAutoField(primary_key=True)
	player1 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player1", db_column="player1", null=True, blank=True)
	player1_score = models.IntegerField()
	player2 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player2", db_column="player2", null=True, blank=True)
	player2_score = models.IntegerField()
	is_tournament = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	winner = models.CharField(max_length=128, null=True, blank=True)

	def save(self, *args, **kwargs):
		if self.player1_score > self.player2_score:
			self.winner = self.player1.username
		elif self.player1_score < self.player2_score:
			self.winner = self.player2.username
		else:
			self.winner = None
		super(SingleGameRecord, self).save(*args, **kwargs)

	def __str__(self):
		return f"single-game-record at {self.created_at}"

class MultiGameRecord(models.Model):
	id = models.BigAutoField(primary_key=True)
	game1 = models.ForeignKey(SingleGameRecord, on_delete=models.CASCADE, related_name="game1", db_column="game1", null=True, blank=True)
	game2 = models.ForeignKey(SingleGameRecord, on_delete=models.CASCADE, related_name="game2", db_column="game2", null=True, blank=True)
	game3 = models.ForeignKey(SingleGameRecord, on_delete=models.CASCADE, related_name="game3", db_column="game3", null=True, blank=True)
	player1 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player1_multi", db_column="player1", null=True, blank=True)
	player2 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player2_multi", db_column="player2", null=True, blank=True)
	player3 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player3_multi", db_column="player3", null=True, blank=True)
	player4 = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="player4_multi", db_column="player4", null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
	def __str__(self):
		return f"multi-game-record at {self.created_at}"

class SingleGameDetail(ExportModelOperationsMixin("game_detail"), models.Model):
	id = models.BigAutoField(primary_key=True)
	game = models.ForeignKey(SingleGameRecord, on_delete=models.CASCADE, db_column="game")
	goal_user_name = models.CharField(max_length=128)
	goal_user_position = models.CharField(max_length=128) # left or right
	ball_start_position = models.CharField(max_length=255) # end 되기 1초 전
	ball_end_position = models.CharField(max_length=255)
	timestamp = models.FloatField()
