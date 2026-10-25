"""Independent project entry points; all paths are relative to --root."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .common import atomic_json, digest, utcnow


def run(root: Path, profile='full', seed=20261021, operational='snapshot', skip_report=False):
    from .simulation import generate
    from .sources import acquire
    from .event_api import serve
    from .ingestion import ingest_api, build_database, export_normalized
    from .analysis import analyze
    from .quality import validate

    evidence = {'project_id':'DA-E01','started_at':utcnow(),'profile':profile,
                'seed':seed,'operational_mode':operational,'steps':{}}
    def record(name, value):
        evidence['steps'][name]=value
        atomic_json(root/'validation/run_manifest.json',evidence)
        print(f'{name}: completed',flush=True)
    record('public_sources',acquire(root))
    record('generation',generate(root,profile=profile,seed=seed))
    with serve(root) as url:
        ingestion=ingest_api(root,url)
    if not ingestion['counts_reconcile']:
        raise RuntimeError('Source attempts and terminal ingestion dispositions do not reconcile')
    record('http_ingestion',ingestion)
    extracted=None
    if operational=='postgres':
        from .operational import bootstrap, extract
        record('postgresql',bootstrap(root))
        extracted=extract(root)
    record('database',build_database(root,extracted))
    record('analysis',analyze(root))
    report=validate(root)
    record('quality',{'status':report['status'],'report':'validation/quality_report.json'})
    if report['status']!='passed':
        raise RuntimeError('Canonical data quality checks failed; inspect validation/quality_report.json')
    record('parquet',export_normalized(root))
    if not skip_report:
        from .reporting import report as write_report
        record('reporting',write_report(root))
    evidence['finished_at']=utcnow()
    evidence['status']='completed'
    evidence['database_sha256']=digest(root/'data/DA-E01.duckdb')
    atomic_json(root/'validation/run_manifest.json',evidence)
    return evidence


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('run','generate'):
        p=sub.add_parser(name)
        p.add_argument('--profile',choices=['full','smoke'],default='full')
        p.add_argument('--seed',type=int,default=20261021)
        if name=='run':
            p.add_argument('--operational',choices=['snapshot','postgres'],default='snapshot')
            p.add_argument('--skip-report',action='store_true')
    p=sub.add_parser('serve');p.add_argument('--port',type=int,default=8765)
    p=sub.add_parser('ingest');p.add_argument('--url');p.add_argument('--from-start',action='store_true')
    p=sub.add_parser('build');p.add_argument('--operational-dir',type=Path)
    p=sub.add_parser('sources');p.add_argument('--refresh',action='store_true')
    for name in ('analyze','validate','report','export','postgres-bootstrap','postgres-extract'):
        sub.add_parser(name)
    args=parser.parse_args(argv);root=args.root.resolve()
    if not (root/'contracts/da_e01_contract.json').exists():
        parser.error('--root must identify the project directory containing contracts/')
    if args.command=='run':
        result=run(root,args.profile,args.seed,args.operational,args.skip_report)
        print(json.dumps({'status':result['status'],'manifest':'validation/run_manifest.json'}))
    elif args.command=='generate':
        from .simulation import generate
        result=generate(root,args.profile,args.seed)
        print(json.dumps({'profile':result['profile'],'rows':result['table_row_counts']}))
    elif args.command=='serve':
        import threading
        from .event_api import serve
        with serve(root,args.port) as url:
            print(url,flush=True)
            try:threading.Event().wait()
            except KeyboardInterrupt:pass
    elif args.command=='ingest':
        from .event_api import serve
        from .ingestion import ingest_api
        if args.url:result=ingest_api(root,args.url,resume=not args.from_start)
        else:
            with serve(root) as url:result=ingest_api(root,url,resume=not args.from_start)
        print(json.dumps(result,indent=2))
    elif args.command=='build':
        from .ingestion import build_database
        print(json.dumps(build_database(root,args.operational_dir),indent=2))
    elif args.command=='sources':
        from .sources import acquire
        print(json.dumps(acquire(root,refresh=args.refresh),indent=2))
    elif args.command=='analyze':
        from .analysis import analyze
        print(json.dumps(analyze(root),default=str,indent=2))
    elif args.command=='validate':
        from .quality import validate
        result=validate(root)
        print(json.dumps({'status':result['status'],'checks':len(result['checks'])}))
        if result['status']!='passed':raise SystemExit(1)
    elif args.command=='report':
        from .reporting import report
        print(json.dumps(report(root),default=str,indent=2))
    elif args.command=='export':
        from .ingestion import export_normalized
        print(json.dumps(export_normalized(root),indent=2))
    elif args.command=='postgres-bootstrap':
        from .operational import bootstrap
        print(json.dumps(bootstrap(root),indent=2))
    elif args.command=='postgres-extract':
        from .operational import extract
        print(extract(root))


if __name__=='__main__':
    main()
