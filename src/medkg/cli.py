import argparse
import json
import sys

from medkg.qa.pipeline import local_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('question',nargs='?')
    parser.add_argument('--serve-stdio',action='store_true')
    parser.add_argument('--phase',type=int,default=3)
    parser.add_argument('--mode',choices=['hybrid','vector'],default='hybrid')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--fake',action='store_true',help='Fictional CI fixture only; no network LLM or embedding calls')
    args = parser.parse_args()
    if args.fake and args.mode=='vector':
        parser.error('FakeLLM fixture mode cannot invoke embedding retrieval')
    if args.fake:
        from medkg.config import Settings
        from medkg.llm import FakeLLM
        from medkg.qa.pipeline import Pipeline
        settings = Settings()
        settings.phase = args.phase
        from medkg.config import ROOT
        entities = json.loads((ROOT/'tests/fixtures/entities.json').read_text(encoding='utf8'))
        pipeline = Pipeline(settings,llm=FakeLLM(),entities=entities,mode=args.mode)
    else:
        pipeline = local_pipeline(args.phase,args.mode)
    try:
        if args.serve_stdio:
            for line in sys.stdin:
                request = json.loads(line)
                print(json.dumps(pipeline.ask(request['question'],request.get('history',[]))),flush=True)
            return
        if not args.question:
            parser.error('A question or --serve-stdio is required')
        result = pipeline.ask(args.question)
        print(json.dumps(result,indent=2) if args.json else result['answer'])
    finally:
        pipeline.close()


if __name__=='__main__':
    main()
