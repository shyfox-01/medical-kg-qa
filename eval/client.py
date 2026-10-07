"""Evaluation calls system and research LLM workers only through public protocols."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


class JSONProcess:
    def __init__(self, command: list[str], timeout: float = 300, environment: dict | None = None):
        self.timeout = timeout
        self.process = subprocess.Popen([sys.executable,*command],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf8',bufsize=1,
            env=environment)
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read,daemon=True)
        self.reader.start()

    def _read(self) -> None:
        for line in self.process.stdout:
            self.responses.put(line)
        self.responses.put(None)

    def request(self, payload: dict) -> dict:
        self.process.stdin.write(json.dumps(payload)+'\n')
        self.process.stdin.flush()
        try:
            line = self.responses.get(timeout=self.timeout)
        except queue.Empty as exc:
            self.close()
            raise TimeoutError('External worker request deadline exceeded') from exc
        if not line:
            raise RuntimeError('External worker exited')
        return json.loads(line)

    def close(self) -> None:
        if not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if os.name=='nt' and self.process.poll() is None:
                subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        if not self.process.stdout.closed:
            self.process.stdout.close()


class SystemClient(JSONProcess):
    def __init__(self, phase: int = 1, mode: str = 'hybrid', fake: bool = False,
                 source: Path | None = None):
        environment = None
        if source is not None:
            environment = dict(os.environ)
            environment['PYTHONPATH'] = str(source.resolve())
            environment['MEDKG_HOME'] = str(Path(__file__).resolve().parents[1])
        super().__init__(['-m','medkg.cli','--serve-stdio','--phase',str(phase),'--mode',mode,
                          *(['--fake'] if fake else [])],environment=environment)

    def ask(self, question: str, history: list[dict]) -> dict:
        return self.request({'question':question,'history':history})


class ResearchLLM(JSONProcess):
    def __init__(self, judge: bool = False):
        super().__init__(['-m','scripts.llm_worker',*(['--judge'] if judge else [])])

    def json(self, system: str, payload: dict, max_tokens: int = 1400) -> dict:
        result = self.request({'messages':[{'role':'system','content':system},
            {'role':'user','content':json.dumps(payload)}],'max_tokens':max_tokens})
        if 'result' not in result:
            raise RuntimeError(result.get('error_type','LLM failed'))
        return result['result']
