# base image
# How to build:
# 1) Go to top of repo
# 2) docker build --tag ghcr.io/slaclab/mps-history-processor:latest -f mps_processor/Dockerfile .

FROM python:3.10.14

# Create a non-root user
RUN useradd -m appuser

# Add mps processor code to /app, and the database and configuration
RUN mkdir /app
COPY mps_processor/ /app/mps_processor
COPY config.py start_history.py /app/
COPY mps_database/ /app/mps_database
COPY mps_configuration/ /app/mps_configuration

# install requirements.txt
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/mps_processor/requirements.txt

# install mps_database
RUN pip install -e /app/mps_database/

# Add env variable for python scripts to stream live
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER appuser
