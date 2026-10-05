"""Evaluation calls system and research LLM workers only through public protocols."""

import json
import subprocess
import sys


class JSONProcess:
    def __init__(self, command: list[str]):
        self.process = subprocess.Popen([sys.executable,*command],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf8',bufsize=1)

    def request(self, payload: dict) -> dict:
        self.process.stdin.write(json.dumps(payload)+'\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('External worker exited')
        return json.loads(line)

    def close(self) -> None:
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdout.close()


class SystemClient(JSONProcess):
    def __init__(self, phase: int = 1, mode: str = 'hybrid', fake: bool = False):
        super().__init__(['-m','medkg.cli','--serve-stdio','--phase',str(phase),'--mode',mode,
                          *(['--fake'] if fake else [])])

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
