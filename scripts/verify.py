"""Run isolated HTTP servers and execute real Jupyter kernels; preserve evidence."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
if sys.platform == 'win32':
    # ZMQ uses add_reader; Proactor's compatibility thread can fail at shutdown.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]

def execute(name):
    path = ROOT / 'notebooks' / name
    book = nbformat.read(path, as_version=4)
    print('Executing', name, flush=True)
    try:
        NotebookClient(book, timeout=600, kernel_name='lab-python',
                       resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        nbformat.write(book, path)
    print('Saved executed', name, flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--http-only', action='store_true')
    args = parser.parse_args()
    runtime = ROOT / '.verification-runtime'
    kernel = runtime / 'kernels' / 'lab-python'
    kernel.mkdir(parents=True, exist_ok=True)
    (ROOT / 'reports').mkdir(exist_ok=True)
    (kernel / 'kernel.json').write_text(json.dumps({
        'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': 'Lab Python', 'language': 'python'}), encoding='utf-8')
    os.environ['JUPYTER_PATH'] = str(runtime)
    os.environ['JUPYTER_RUNTIME_DIR'] = str(runtime)
    os.environ['IPYTHONDIR'] = str(runtime / 'ipython')
    os.environ['TEMP'] = str(runtime)
    os.environ['TMP'] = str(runtime)
    servers = []
    logs = []
    try:
        for mode, port in [('fixture', 8011), ('live', 8012)]:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
            log = (runtime / f'{mode}.log').open('w', encoding='utf-8')
            logs.append(log)
            env = {**os.environ, 'AI_MODE': mode, 'PYTHONIOENCODING': 'utf-8'}
            proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                     '--host', '127.0.0.1', '--port', str(port)],
                                    cwd=ROOT, env=env, stdout=log, stderr=log,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            servers.append(proc)
            import requests
            for attempt in range(60):
                if proc.poll() is not None:
                    raise RuntimeError(f'{mode} server exited; see {runtime / (mode+".log")}')
                try:
                    response = requests.get(f'http://127.0.0.1:{port}/videos', timeout=1)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError(f'{mode} server did not become ready')
            print(f'{mode} server ready on {port}', flush=True)
        os.environ['VERIFY_URL'] = 'http://127.0.0.1:8011'
        os.environ['LIVE_VERIFY_URL'] = 'http://127.0.0.1:8012'
        if not args.http_only:
            execute('01_experiment.ipynb')
        execute('02_api_verification.ipynb')
        shutil.copy2(ROOT/'reports/http-verification.json', ROOT/'reports/http-first-pass.json')
        execute('02_api_verification.ipynb')
        shutil.copy2(ROOT/'reports/http-verification.json', ROOT/'reports/http-repeat-pass.json')
        print('Both HTTP passes completed. Test processes will stop; memory data discarded.', flush=True)
    finally:
        for proc in servers:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for log in logs:
            log.close()
    print('Verification finished; all test processes stopped.', flush=True)

if __name__ == '__main__':
    main()
