"""Dedicated worker entry point; no web process is needed to keep time."""
import os
import time
os.environ['EMBEDDED_FLOW_WORKER']='false'
from core import create_app
from services.flow_worker import run_once
app=create_app()
while True:
    try: run_once(app)
    except Exception: app.logger.exception('Dedicated recovery cycle failed')
    time.sleep(60)
