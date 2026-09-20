import subprocess,json,pathlib,time,datetime,threading,sys
NAME='BigTank/agent-concurrency-20260920';DIR='/mnt/'+NAME;created=False
DEV=['sdg','sdh','sdi','sdj']
def emit(kind,**kw):print(json.dumps(dict(kind=kind,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw)),flush=True)
def cmd(a):
 p=subprocess.run(a,capture_output=True,text=True,timeout=30)
 if p.returncode:raise RuntimeError(str(a)+p.stderr)
 return p.stdout

def safety():
 t={}
 for d in DEV:
  j=json.loads(subprocess.run(['sudo','-n','smartctl','-a','-j','/dev/'+d],capture_output=True,text=True,timeout=10).stdout);t[d]=j['temperature']['current']
 if max(t.values())>=60:raise RuntimeError('temperature stop'+str(t))
 if cmd(['zpool','status','-x']).strip()!='all pools are healthy':raise RuntimeError('pool unhealthy')
 return t

def snap():
 a=[l.split() for l in pathlib.Path('/proc/diskstats').read_text().splitlines()]
 return {r[2]:list(map(int,r[3:])) for r in a if r[2] in DEV}
def run(name,opts):
 args=['sudo','-n','fio','--name='+name,'--ioengine=psync','--iodepth=1','--bs=1M','--direct=0','--invalidate=0','--group_reporting=0','--output-format=json','--runtime=90']+opts
 emit('start',name=name,argv=args,temperatures=safety());before=snap();started=time.monotonic();p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);stop=threading.Event();errors=[];temps=[]
 def monitor():
  while not stop.wait(10):
   try:temps.append(safety())
   except Exception as e:errors.append(str(e));p.terminate();return
 m=threading.Thread(target=monitor,daemon=True);m.start()
 try:out,err=p.communicate(timeout=120)
 except Exception:p.terminate();out,err=p.communicate(timeout=10);raise
 finally:elapsed=time.monotonic()-started;stop.set()
 after=snap();m.join(timeout=15)
 if p.returncode or errors:raise RuntimeError(str(errors)+err+out[:300])
 j=json.loads(out);result=[]
 for i,x in enumerate(j['jobs']):
  if x['error']:raise RuntimeError('fio job error')
  d='write' if x['write']['io_bytes'] else 'read';r=x[d]
  result.append(dict(job_index=i,jobname=x['jobname'],direction=d,bytes=r['io_bytes'],runtime_ms=r['runtime'],MBs=r['bw_bytes']/1e6,iops=r['iops'],clat_mean_ms=r['clat_ns']['mean']/1e6,p99_ms=r['clat_ns'].get('percentile',{}).get('99.000000',0)/1e6))
 total=sum(x['bytes'] for x in result);maxruntime=max(x['runtime_ms'] for x in result)
 emit('result',name=name,jobs=result,total_bytes=total,wall_seconds=elapsed,aggregate_wall_MBs=total/elapsed/1e6,aggregate_max_job_runtime_MBs=total/(maxruntime/1000)/1e6,physical_read_MiB=sum(after[d][2]-before[d][2] for d in DEV)*512/2**20,physical_write_MiB=sum(after[d][6]-before[d][6] for d in DEV)*512/2**20,temperatures_during=temps,temperatures_after=safety(),fio=j)
try:
 emit('preflight',temperatures=safety(),pool=cmd(['zpool','list','BigTank']))
 if subprocess.run(['zfs','list','-H',NAME],capture_output=True).returncode==0:raise RuntimeError('dataset already exists')
 cmd(['midclt','call','pool.dataset.create',json.dumps(dict(name=NAME,type='FILESYSTEM',compression='OFF',atime='OFF',sync='STANDARD',recordsize='128K',quota=8589934592))]);created=True
 cmd(['sudo','-n','zfs','set','primarycache=metadata','secondarycache=none',NAME]);emit('dataset',name=NAME,properties=cmd(['zfs','get','-Hp','compression,atime,sync,recordsize,primarycache,secondarycache,quota',NAME]))
 common=['--directory='+DIR,'--filename_format=payload.$jobnum','--numjobs=4','--size=1G']
 run('four-concurrent-writers-flushed',common+['--rw=write','--end_fsync=1'])
 emit('files',files=[dict(name='payload.'+str(i),size=pathlib.Path(DIR+'/payload.'+str(i)).stat().st_size,allocated=pathlib.Path(DIR+'/payload.'+str(i)).stat().st_blocks*512) for i in range(4)])
 run('one-reader-four-files',['--filename='+':'.join(DIR+'/payload.'+str(i) for i in range(4)),'--numjobs=1','--size=4G','--nrfiles=4','--file_service_type=sequential','--rw=read','--readonly','--allow_file_create=0'])
 run('four-concurrent-readers',common+['--rw=read','--readonly','--allow_file_create=0'])
 cmd(['midclt','call','pool.dataset.delete',NAME]);created=False;emit('deleted',name=NAME)
 emit('complete',health=cmd(['zpool','status','-x']),temperatures=safety())
except Exception as e:emit('error',error=str(e));sys.exitcode=1
finally:
 if created:
  try:cmd(['midclt','call','pool.dataset.delete',NAME]);emit('cleanup_deleted',name=NAME)
  except Exception as e:emit('cleanup_error',error=str(e))
 if getattr(sys,'exitcode',0):sys.exit(1)
