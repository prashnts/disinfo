[program:di2study]
command=/home/noop/run/disinfo/.venv/bin/python -m disinfo.renderers.background --fps 48
directory=/home/noop/run/disinfo
user=noop
environment=DI_CONFIG_PATH=".config-study.json"
