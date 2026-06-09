# Variables
SERVICE_NAME = paperclip-ai
USER = $(shell whoami)
NPX = $(shell which npx)
HOME_DIR = $(HOME)
# Hostnames/IPs to allow during setup (space-separated)
# Usage: make pm2-setup HOSTS="192.168.1.10 paperclip.zakariafadli.com"
HOSTS ?= 192.168.1.10 paperclip.zakariafadli.com

.PHONY: help install pm2-setup pm2-stop pm2-status pm2-restart pm2-logs systemd-setup systemd-stop systemd-status systemd-restart systemd-logs restart logs clean

help:
	@echo "Paperclip AI Service Automation"
	@echo "==============================="
	@echo "Usage:"
	@echo "  make install         - Install paperclipai globally"
	@echo "  make pm2-setup       - Setup and start background service using PM2 (Recommended)"
	@echo "  make pm2-stop        - Stop and remove PM2 service"
	@echo "  make pm2-status      - Show PM2 service status"
	@echo "  make systemd-setup   - Setup and start background service using systemd"
	@echo "  make systemd-stop    - Stop and remove systemd service"
	@echo "  make systemd-status  - Show systemd service status"
	@echo "  make restart         - Restart the service (smart detection)"
	@echo "  make logs            - Show logs (smart detection)"
	@echo "  make clean           - Stop and remove both PM2 and systemd services"
	@echo ""
	@echo "Options:"
	@echo "  HOSTS=\"h1 h2\"      - Specify hostnames/IPs to allow during setup"
	@echo "                         (default: \"192.168.1.10 paperclip.zakariafadli.com\")"

install:
	@echo "Installing paperclipai globally..."
	npm install -g paperclipai

pm2-setup:
	@echo "Setting up PM2 service..."
	pm2 start paperclipai --name "$(SERVICE_NAME)" -- onboard --yes --bind lan
	@echo "Allowing hostnames: $(HOSTS)..."
	@for host in $(HOSTS); do \
		$(NPX) paperclipai allowed-hostname $$host; \
	done
	@echo "Generating startup script. Follow instructions if prompted for sudo."
	pm2 startup | grep "sudo" | bash || echo "Please run the 'pm2 startup' command manually and follow instructions."
	pm2 save
	@echo "PM2 setup complete."

pm2-stop:
	-pm2 stop $(SERVICE_NAME)
	-pm2 delete $(SERVICE_NAME)
	pm2 save

pm2-status:
	pm2 status $(SERVICE_NAME)

pm2-restart:
	pm2 restart $(SERVICE_NAME)

pm2-logs:
	pm2 logs $(SERVICE_NAME)

systemd-setup:
	@echo "Creating systemd service file..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Paperclip AI Daemon" >> $(SERVICE_NAME).service
	@echo "After=network.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "Restart=on-failure" >> $(SERVICE_NAME).service
	@echo "RestartSec=10" >> $(SERVICE_NAME).service
	@echo "WorkingDirectory=$(HOME_DIR)" >> $(SERVICE_NAME).service
	@echo "ExecStart=$(NPX) paperclipai onboard --yes --bind lan" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Install]" >> $(SERVICE_NAME).service
	@echo "WantedBy=multi-user.target" >> $(SERVICE_NAME).service
	@echo "Moving service file to /etc/systemd/system/ (requires sudo)..."
	sudo mv $(SERVICE_NAME).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_NAME)
	sudo systemctl start $(SERVICE_NAME)
	@echo "Allowing hostnames: $(HOSTS)..."
	@for host in $(HOSTS); do \
		$(NPX) paperclipai allowed-hostname $$host; \
	done
	sudo systemctl restart $(SERVICE_NAME)
	@echo "Systemd service setup complete."

systemd-stop:
	@echo "Stopping and disabling systemd service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	sudo systemctl daemon-reload

systemd-status:
	sudo systemctl status $(SERVICE_NAME)

systemd-restart:
	sudo systemctl restart $(SERVICE_NAME)

systemd-logs:
	sudo journalctl -u $(SERVICE_NAME) -f

restart:
	@if pm2 describe $(SERVICE_NAME) > /dev/null 2>&1; then \
		echo "Restarting PM2 service..."; \
		pm2 restart $(SERVICE_NAME); \
	fi
	@if systemctl list-unit-files $(SERVICE_NAME).service | grep -q $(SERVICE_NAME).service; then \
		echo "Restarting systemd service..."; \
		sudo systemctl restart $(SERVICE_NAME); \
	fi

logs:
	@if pm2 describe $(SERVICE_NAME) > /dev/null 2>&1; then \
		echo "Showing PM2 logs..."; \
		pm2 logs $(SERVICE_NAME) --lines 20 --no-daemon; \
	fi
	@if systemctl list-unit-files $(SERVICE_NAME).service | grep -q $(SERVICE_NAME).service; then \
		echo "Showing systemd logs..."; \
		sudo journalctl -u $(SERVICE_NAME) -n 20 --no-pager; \
	fi

clean:
	@echo "Cleaning up all services..."
	-pm2 delete $(SERVICE_NAME)
	-pm2 save
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	-sudo systemctl daemon-reload
