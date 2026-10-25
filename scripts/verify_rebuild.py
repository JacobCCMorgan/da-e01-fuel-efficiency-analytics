"""Prove a clean build from source inputs, then optionally vary one parameter.

Example:
  python scripts/verify_rebuild.py --work-dir /tmp/fuel-clean --stage all
  python scripts/verify_rebuild.py --work-dir /tmp/fuel-clean --stage parameters

The work directory must be outside the project. A prepared directory is never
silently deleted. No database, generated fleet file, staging receipt or analytical
output is copied from the reference build.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


SET_JSON_FIELDS = {'input_provenance_ids', 'parent_provenance_ids'}


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n')


def ignored(_directory, names):
    return [name for name in names if name.startswith('.') or name=='__pycache__'
            or name.endswith(('.tmp','.pyc','.wal'))]


def prepare(reference: Path, target: Path, seed: int | None=None):
    if target == reference or reference in target.parents:
        raise ValueError('Keep the isolated rebuild outside the reference project')
    if target.exists():
        raise FileExistsError(f'Refusing to overwrite an existing rebuild: {target}')
    target.mkdir(parents=True)
    for name in ['src','sql','contracts','config','scripts']:
        shutil.copytree(reference/name, target/name, ignore=ignored)
    for name in ['pyproject.toml','requirements.lock']:
        if (reference/name).is_file():
            shutil.copy2(reference/name,target/name)
    # Cached official source files and their original receipts are frozen
    # inputs. They are distinct from generated vehicle source files.
    shutil.copytree(reference/'data/public',target/'data/public',ignore=ignored)
    (target/'validation').mkdir(exist_ok=True)
    junit=reference/'validation/test_results.xml'
    if junit.exists():
        shutil.copy2(junit,target/'validation/test_results.xml')
    if seed is not None:
        for name in ['project','simulation']:
            path=target/'config'/f'{name}.json'
            value=json.loads(path.read_text());value['seed']=seed;save(path,value)
    copied=[{'path':p.relative_to(target).as_posix(),'sha256':digest(p)}
            for p in sorted(target.rglob('*')) if p.is_file()]
    evidence={'copied_inputs':copied,'copied_generated_data':False,
              'initial_database_exists':(target/'data/DA-E01.duckdb').exists(),
              'initial_generated_raw_exists':(target/'data/raw').exists(),
              'initial_analytical_outputs_exist':(target/'outputs').exists(),
              'junit_policy':'Reference source-code test evidence is reused; actual pipeline quality is executed again.'}
    save(target/'validation/rebuild_inputs.json',evidence)
    return evidence


def run_pipeline(target: Path, profile: str, seed: int):
    command=[sys.executable,'-m','fleet_fuel.cli','--root',str(target),'run',
             '--profile',profile,'--seed',str(seed),'--operational','snapshot','--skip-report']
    env=os.environ.copy();env['PYTHONPATH']=str(target/'src')
    started=datetime.now(timezone.utc).isoformat();before=time.monotonic()
    log=target/'validation/rebuild_execution.log'
    with log.open('w') as stream:
        process=subprocess.Popen(command,cwd=target,env=env,stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,text=True,bufsize=1)
        for line in process.stdout:
            stream.write(line);stream.flush();print(line,end='',flush=True)
        code=process.wait()
    evidence={'profile':profile,'seed':seed,'operational_mode':'snapshot',
              'event_ingestion':'actual HTTP requests to the local simulated ELD service',
              'public_source_mode':'hash-verified frozen official snapshot; no new network download claimed',
              'started_at':started,'elapsed_seconds':round(time.monotonic()-before,3),
              'exit_code':code,'log_sha256':digest(log),
              'entry_point':'python -m fleet_fuel.cli --root <isolated> run --profile '+profile+
                            ' --seed '+str(seed)+' --operational snapshot --skip-report'}
    save(target/'validation/rebuild_execution.json',evidence)
    if code:
        raise RuntimeError(f'Isolated pipeline failed with exit code {code}; see {log}')
    return evidence


def json_default(value):
    if isinstance(value,(datetime,date)):
        return value.isoformat()
    if isinstance(value,Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def logical_table_hash(connection, table, fields):
    names=[f['name'] for f in fields]
    quoted=lambda name:'"'+name.replace('"','""')+'"'
    ordering=table['primary_key']
    cursor=connection.execute('SELECT '+','.join(map(quoted,names))+' FROM normalized.'+
                              quoted(table['name'])+' ORDER BY '+','.join(map(quoted,ordering)))
    json_positions={i:names[i] for i,f in enumerate(fields) if f['type']=='JSON'}
    checksum=hashlib.sha256();count=0
    for batch in iter(lambda:cursor.fetchmany(2000),[]):
        for row in batch:
            value=list(row)
            for index,name in json_positions.items():
                if value[index] is not None:
                    item=json.loads(value[index]) if isinstance(value[index],str) else value[index]
                    if name in SET_JSON_FIELDS and isinstance(item,list):
                        item=sorted(item,key=lambda x:json.dumps(x,sort_keys=True))
                    value[index]=item
            checksum.update((json.dumps(value,sort_keys=True,ensure_ascii=False,
                                        separators=(',',':'),default=json_default)+'\n').encode())
            count+=1
    return {'rows':count,'sha256':checksum.hexdigest()}


def compare_csv(reference, rebuilt):
    with reference.open() as left,rebuilt.open() as right:
        a=list(csv.DictReader(left));b=list(csv.DictReader(right))
    errors=[];different=0;maximum=0.0
    if len(a)!=len(b):
        return {'status':'failed','reference_rows':len(a),'rebuilt_rows':len(b),'reason':'row_count'}
    for index,(x,y) in enumerate(zip(a,b)):
        if x.keys()!=y.keys():
            return {'status':'failed','reason':'column_set'}
        for key,first in x.items():
            second=y[key]
            if first==second:continue
            equal=False
            try:
                f=float(Decimal(first));s=float(Decimal(second))
                maximum=max(maximum,abs(f-s))
                equal=math.isclose(f,s,rel_tol=1e-10,abs_tol=1e-7)
            except (InvalidOperation,ValueError,TypeError):pass
            if not equal:
                different+=1
                if len(errors)<5:errors.append({'row':index+1,'column':key,'reference':first,'rebuilt':second})
    return {'status':'passed' if not different else 'failed','rows':len(a),
            'different_cells':different,'maximum_numeric_difference':maximum,'examples':errors,
            'numeric_tolerance':'relative 1e-10 or absolute 1e-7; text is exact'}


def compare(reference: Path, target: Path):
    import duckdb
    contract=json.loads((reference/'contracts/da_e01_contract.json').read_text())
    comparisons=[]
    with duckdb.connect(str(reference/'data/DA-E01.duckdb'),read_only=True) as a, \
         duckdb.connect(str(target/'data/DA-E01.duckdb'),read_only=True) as b:
        a.execute("SET TimeZone='UTC'");b.execute("SET TimeZone='UTC'")
        for table in contract['tables']:
            fields=[f for f in contract['fields'] if f['table']==table['name']]
            x=logical_table_hash(a,table,fields);y=logical_table_hash(b,table,fields)
            comparisons.append({'table':table['name'],'reference':x,'rebuilt':y,'equal':x==y})
            print('table comparison:',table['name'],'equal' if x==y else 'DIFFERENT',flush=True)
    manifest=json.loads((reference/'data/generation_manifest.json').read_text())
    sources=[]
    for item in manifest['sources']:
        name=item['path'];a=reference/name;b=target/name
        one=digest(a) if a.is_file() else None;two=digest(b) if b.is_file() else None
        sources.append({'path':name,'reference_sha256':one,'rebuilt_sha256':two,'equal':one is not None and one==two})
    outputs={name:compare_csv(reference/'outputs'/name,target/'outputs'/name)
             for name in ['fleet_weekly.csv','report_revisions.csv','coverage_sensitivity.csv']}
    actual=json.loads((target/'validation/quality_report.json').read_text())
    summary_a=json.loads((reference/'outputs/analytics_summary.json').read_text())['totals']
    summary_b=json.loads((target/'outputs/analytics_summary.json').read_text())['totals']
    totals={key:{'reference':value,'rebuilt':summary_b[key],
                 'equal':math.isclose(value,summary_b[key],rel_tol=1e-10,abs_tol=1e-7)
                         if isinstance(value,(int,float)) and summary_b[key] is not None else value==summary_b[key]}
            for key,value in summary_a.items()}
    result={'logical_tables':comparisons,'generated_source_bytes':sources,'kpi_totals':totals,
            'kpi_output_files':outputs,'clean_quality':{'status':actual['status'],'checks':len(actual['checks']),
                                                      'error_count':actual['error_count']},
            'normalization':{'row_order':'canonical primary keys','json_objects':'sorted keys',
                             'unordered_json_arrays':sorted(SET_JSON_FIELDS),
                             'timestamps':'preserved without replacing source or availability times',
                             'database_binary_bytes':'not compared; storage layout is not logical data'},
            'report_generation':'excluded from this proof; charts are validated separately'}
    result['status']='passed' if (all(x['equal'] for x in comparisons+sources)
        and all(x['equal'] for x in totals.values()) and all(x['status']=='passed' for x in outputs.values())
        and actual['status']=='passed') else 'failed'
    return result


def parameters(reference: Path, work: Path, seed: int):
    results={}
    for label,value in [('baseline',seed),('changed_seed',seed+1)]:
        target=work.parent/(work.name+'_parameter_'+label)
        prepare(reference,target,value);execution=run_pipeline(target,'smoke',value)
        summary=json.loads((target/'outputs/analytics_summary.json').read_text())
        quality=json.loads((target/'validation/quality_report.json').read_text())
        results[label]={'profile':'smoke','seed':value,'execution':execution,
                        'totals':summary['totals'],'quality_status':quality['status'],
                        'quality_error_count':quality['error_count'],
                        'trip_plan_sha256':digest(target/'data/raw/operations/trip_plan.jsonl'),
                        'vehicle_weekly_sha256':digest(target/'outputs/vehicle_weekly.csv')}
    a,b=results['baseline'],results['changed_seed']
    changed=[key for key in a['totals'] if a['totals'][key]!=b['totals'][key]]
    return {'status':'passed' if changed and a['trip_plan_sha256']!=b['trip_plan_sha256']
            and a['vehicle_weekly_sha256']!=b['vehicle_weekly_sha256']
            and all(r['quality_status']=='passed' for r in results.values()) else 'failed',
            'one_changed_parameter':'seed; profile remains smoke in both runs',
            'changed_kpis':changed,'runs':results,
            'interpretation':'The configurable data-generating process and downstream output respond to a seed change while contractual invariants remain valid. This is a software test, not a measured fleet effect.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--stage',choices=['all','prepare','run','compare','parameters'],default='all')
    args=parser.parse_args();root=args.root.resolve();work=args.work_dir.resolve()
    path=root/'validation/rebuild_report.json'
    report=json.loads(path.read_text()) if path.exists() else {'project_id':'DA-E01','schema_version':'1.0.0','status':'in_progress'}
    seed=json.loads((root/'config/project.json').read_text())['seed']
    try:
        if args.stage in {'all','prepare'}:
            report['isolation']=prepare(root,work);save(path,report)
        if args.stage in {'all','run'}:
            report['execution']=run_pipeline(work,'full',seed);save(path,report)
        if args.stage in {'all','compare'}:
            report['comparison']=compare(root,work);report['status']=report['comparison']['status'];save(path,report)
        if args.stage=='parameters':
            report['parameter_change']=parameters(root,work,seed)
            report['status']='passed' if report.get('comparison',{}).get('status')=='passed' and report['parameter_change']['status']=='passed' else 'failed'
            save(path,report)
    except Exception as error:
        report['status']='failed';report['error']=str(error);save(path,report);raise
    print('rebuild evidence:',report['status'],flush=True)
    if report['status']=='failed':raise SystemExit(1)


if __name__=='__main__':main()
