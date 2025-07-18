FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

COPY debian-requirements.txt debian-requirements.txt
RUN apt-get update
RUN xargs -a debian-requirements.txt sudo apt-get install -y
