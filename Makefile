# =============================================
# SHELL
# =============================================
SHELL 						:= /bin/bash

# =============================================
# VARIABLES
# =============================================
# UNAME_S 					:= $(shell uname -s)

SRC_FOLDER				:= .
FE_FOLDER				:= frontend
BE_FOLDER				:= backend
NGINX_FOLDER			:= nginx
REDIS_FOLDER			:= redis
CONFIG_FOLDER			:= config
PROMETHEUS_FOLDER		:= prometheus
GRAFANA_FOLDER			:= grafana
CERTIFICATE_FOLDER		:= cert
ELASTIC_PASSWORD		:= abc123

FE_PATH					:= $(SRC_FOLDER)/$(FE_FOLDER)
BE_PATH					:= $(SRC_FOLDER)/$(BE_FOLDER)
NGINX_PATH				:= $(SRC_FOLDER)/$(NGINX_FOLDER)
REDIS_PATH				:= $(SRC_FOLDER)/$(REDIS_FOLDER)
PROMETHEUS_PATH			:= $(SRC_FOLDER)/$(PROMETHEUS_FOLDER)
GRAFANA_PATH			:= $(SRC_FOLDER)/$(GRAFANA_FOLDER)
CERTIFICATE_PATH		:= $(SRC_FOLDER)/$(CERTIFICATE_FOLDER)

export FE_PATH BE_PATH NGINX_PATH REDIS_PATH PROMETHEUS_PATH GRAFANA_PATH CERTIFICATE_PATH ELASTIC_PASSWORD

ifeq ($(firstword $(MAKECMDGOALS)),local)
	ENV_FILE				:= .env.local
else
	ENV_FILE 				:= .env
endif

FE_ENV_PATH 			:= $(SRC_FOLDER)/$(CONFIG_FOLDER)/$(FE_FOLDER)/$(ENV_FILE)
BE_ENV_PATH 			:= $(SRC_FOLDER)/$(CONFIG_FOLDER)/$(BE_FOLDER)/$(ENV_FILE)
export FE_ENV_PATH BE_ENV_PATH

EXECTUE_FE_CMD		:= cd $(PWD) &&																										\
											cd $(FE_PATH) && 																							\
											npm run dev
EXECTUE_BE_CMD		:= cd $(PWD) &&																										\
											python3 -m venv ~/goinfre/venv && 													\
											source ~/goinfre/venv/bin/activate &&             \
											cd $(BE_PATH) &&																							\
											export ENV=local &&																						\
											pip3 install -r requirements.txt &&														\
											python3 manage.py makemigrations &&														\
											python3 manage.py migrate &&																	\
											python3 manage.py runserver 0.0.0.0:8000

NAME							:= .transcendence

# =============================================
# ENVIRONMENT VARIABLE FOR DOCKER COMPOSE
# =============================================
ifeq ($(firstword $(MAKECMDGOALS)),local)
	COMPOSE_FILE 		:= docker-compose.local.yml
else
	COMPOSE_FILE 		:= docker-compose.yml
endif

# =============================================
# GENERAL RULES
# =============================================
all: $(NAME)

$(NAME):
	docker compose -f $(COMPOSE_FILE) up -d

local:
	docker compose -f $(COMPOSE_FILE) up -d
# $(MAKE) frontend
# $(MAKE) backend

frontend:
	@osascript -e 																																		\
	'tell application "iTerm" to create window with default profile' -e								\
	'tell application "iTerm" to tell current session of current window to write text \
		"$(EXECTUE_FE_CMD)"'
# @$(EXECTUE_FE_CMD)

backend:
	@osascript -e 																																		\
	'tell application "iTerm" to create window with default profile' -e 							\
	'tell application "iTerm" to tell current session of current window to write text \
		"$(EXECTUE_BE_CMD)"'
# @$(EXECTUE_BE_CMD)

clean:
	docker compose down
#rm backend/log/*.log
fclean:
	make clean
	docker system prune --all --volumes --force
	unset ENV
	rm -f $(NAME)

backend-restart:
	docker compose -f $(COMPOSE_FILE) restart backend

frontend-restart:
	docker compose -f $(COMPOSE_FILE) restart frontend

nginx-restart:
	docker compose -f $(COMPOSE_FILE) restart nginx

re:
	make fclean
	make all

.PHONY: all clean fclean re frontend backend

# =============================================
# DOCKER MONITORING
# =============================================
status: ps images volume network top

.PHONY: status

ps logs images top:
	docker compose $@

.PHONY: ps logs images top

network volume:
	docker $@ ls

.PHONY: network volume
