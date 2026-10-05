import json
import sys

from medkg.ingest.extract import extract
from medkg.llm import LLMClient


def main() -> None:
    llm = LLMClient()
    for line in sys.stdin:
        request = json.loads(line)
        try:
            results = extract(llm,request['text'],request.get('mode','openfda'))
            print(json.dumps({'relations':[r.model_dump() for r in results]}),flush=True)
        except Exception as exc:
            print(json.dumps({'relations':[],'error_type':type(exc).__name__}),flush=True)


if __name__=='__main__':
    main()
