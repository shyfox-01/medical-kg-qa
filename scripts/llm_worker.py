"""External research-call protocol with the same task-wide token ledger."""

import json
import sys

from medkg.config import Settings
from medkg.llm import LLMClient


def main() -> None:
    settings = Settings()
    client = LLMClient(settings,settings.judge_model if '--judge' in sys.argv else None)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            output = client.chat_json(request['messages'],request.get('max_tokens',1400))
            print(json.dumps({'result':output,'usage':client.usage}),flush=True)
        except Exception as exc:
            print(json.dumps({'error_type':type(exc).__name__}),flush=True)


if __name__=='__main__':
    main()
