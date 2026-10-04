#!/bin/sh
redis-server --save '' --appendonly no --daemonize yes
python -m disinfo.drat.data_service &
python -m disinfo.renderers.background --fps 30 &
exec uvicorn disinfo.web.server:app --host 0.0.0.0 --port 4200
