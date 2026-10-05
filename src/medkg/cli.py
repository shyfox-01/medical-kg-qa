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
    args = parser.parse_args()
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
