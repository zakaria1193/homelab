# Variables
SERVICE_NAME = paperclip-ai
USER = $(shell whoami)
NPX = $(shell which npx)
HOME_DIR = $(HOME)
# Inherit current PATH to ensure binaries like 'claude' are found by the service
PATH_VAL = $(shell echo $$PATH)
# Hostnames/IPs to allow during setup (space-separated)
HOSTS ?= 192.168.1.10 paperclip.zakariafadli.com

.PHONY: help install systemd-setup systemd-stop systemd-status systemd-restart systemd-logs restart logs clean

help:
	@echo "Paperclip AI Service Automation"
	@echo "==============================="
	@echo "Usage:"
	@echo "  make install         - Install paperclipai globally"
	@echo "  make systemd-setup   - Setup and start background service using systemd"
	@echo "  make systemd-stop    - Stop and remove systemd service"
	@echo "  make systemd-status  - Show systemd service status"
	@echo "  make restart         - Restart the systemd service"
	@echo "  make logs            - Show systemd service logs"
	@echo "  make clean           - Stop and remove the systemd service"
	@echo ""
	@echo "Options:"
	@echo "  HOSTS=\"h1 h2\"      - Specify hostnames/IPs to allow during setup"

install:
	@echo "Installing paperclipai globally..."
	npm install -g paperclipai

systemd-setup:
	@echo "Creating systemd service file..."
	@echo "[Unit]" > $(SERVICE_NAME).service
	@echo "Description=Paperclip AI Daemon" >> $(SERVICE_NAME).service
	@echo "After=network.target" >> $(SERVICE_NAME).service
	@echo "" >> $(SERVICE_NAME).service
	@echo "[Service]" >> $(SERVICE_NAME).service
	@echo "Type=simple" >> $(SERVICE_NAME).service
	@echo "User=$(USER)" >> $(SERVICE_NAME).service
	@echo "Environment=\"PATH=$(PATH_VAL)\"" >> $(SERVICE_NAME).service
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
	@echo "Restarting systemd service..."
	sudo systemctl restart $(SERVICE_NAME)

logs:
	@echo "Showing systemd logs..."
	sudo journalctl -u $(SERVICE_NAME) -n 20 --no-pager

clean:
	@echo "Cleaning up systemd service..."
	-sudo systemctl stop $(SERVICE_NAME)
	-sudo systemctl disable $(SERVICE_NAME)
	-sudo rm -f /etc/systemd/system/$(SERVICE_NAME).service
	-sudo systemctl daemon-reload
