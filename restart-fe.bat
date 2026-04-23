@echo off
cd /d "C:\Users\admin\Documents\zen\portal"
docker -H npipe:////./pipe/docker_engine compose up -d frontend
