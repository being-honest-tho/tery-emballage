#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lance Tery-Emballage en arrière-plan, détaché de la session courante.
Usage : python3 start.py   (ou ./start.py)
Le serveur répond ensuite sur http://127.0.0.1:8791 (log : /tmp/tery-emballage.log)
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
LOG = "/tmp/tery-emballage.log"

# Déjà en ligne ?
s = socket.socket()
s.settimeout(0.4)
try:
    s.connect(("127.0.0.1", PORT))
    s.close()
    print(f"✅ Tery-Emballage déjà en ligne : http://127.0.0.1:{PORT}")
    sys.exit(0)
except OSError:
    pass
finally:
    s.close()

cmd = [
    sys.executable, "-c",
    "from app import app, init_db; init_db(); "
    f"app.run(host='0.0.0.0', port={PORT}, debug=True, use_reloader=False)",
]
logf = open(LOG, "a")
subprocess.Popen(
    cmd, cwd=BASE, start_new_session=True,
    stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
)
for _ in range(8):
    time.sleep(1.5)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3)
        print(f"✅ Tery-Emballage en ligne : http://127.0.0.1:{PORT}   (log : {LOG})")
        sys.exit(0)
    except Exception:
        continue
print("❌ Échec du démarrage — voir le log :", LOG)
sys.exit(1)
