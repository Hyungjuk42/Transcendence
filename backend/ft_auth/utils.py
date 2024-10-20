from django.core.mail import send_mail
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

def send_email(sender_email, receiver_email, app_password, subject, text, html):
	message = MIMEMultipart("alternative")
	message["Subject"] = subject
	message["From"] = sender_email
	message["To"] = receiver_email

	part1 = MIMEText(text, "plain")
	part2 = MIMEText(html, "html")

	message.attach(part1)
	message.attach(part2)

	with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
		server.login(sender_email, app_password)
		server.sendmail(sender_email, receiver_email, message.as_string())