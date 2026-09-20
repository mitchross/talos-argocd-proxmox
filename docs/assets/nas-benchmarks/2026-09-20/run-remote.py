import subprocess,json,pathlib,time,datetime,sys
RUN='agent-bench-20260920-1745'
POOLS={'BigTank':['sdg','sdh','sdi','sdj'],'ai-pool':['sda','sdb','sdc'],'Backup10T':['sdf']}
CREATED=[]
def emit(kind,**kw): print(json.dumps(dict(kind=kind,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw)),flush=True)
def cmd(args,timeout=30):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if p.returncode: raise RuntimeError(str(args)+': '+p.stderr[:500]+p.stdout[:500])
 return p.stdout

def snap():
 rows=[l.split() for l in pathlib.Path('/proc/diskstats').read_text().splitlines()]
 disk={r[2]:list(map(int,r[3:])) for r in rows if r[2] in sum(POOLS.values(),[])}
 arc={r[0]:int(r[2]) for l in pathlib.Path('/proc/spl/kstat/zfs/arcstats').read_text().splitlines()[2:] if len(r:=l.split())==3}
 cpu=list(map(int,pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
 return dict(time=time.monotonic(),disk=disk,arc=arc,cpu=cpu,load=pathlib.Path('/proc/loadavg').read_text().strip())
def temperatures():
 out={}
 for d in ['sdg','sdh','sdi','sdj','sdf']:
  p=subprocess.run(['sudo','-n','smartctl','-a','-j','/dev/'+d],capture_output=True,text=True,timeout=10)
  j=json.loads(p.stdout);out[d]=j.get('temperature',{}).get('current')
 return out

def safety():
 t=temperatures()
 if any(v is not None and v>=60 for v in t.values()): raise RuntimeError('Conservative60C temperature stop: '+str(t))
 health=cmd(['zpool','status','-x']).strip()
 if health!='all pools are healthy': raise RuntimeError('Pool health changed: '+health)
 return t

def delta(before,after,devices):
 dt=after['time']-before['time']; c=[x-y for x,y in zip(after['cpu'],before['cpu'])]
 def total(idx):return sum(after['disk'][d][idx]-before['disk'][d][idx] for d in devices)
 return dict(seconds=dt,physical_read_MiB=total(2)*512/2**20,physical_write_MiB=total(6)*512/2**20,physical_read_iops=total(0)/dt,physical_write_iops=total(4)/dt,cpu_busy_pct=100*(sum(c)-c[3]-c[4])/sum(c),cpu_iowait_pct=100*c[4]/sum(c),arc_delta={k:after['arc'][k]-before['arc'][k] for k in ['hits','misses','demand_data_hits','demand_data_misses','l2_hits','l2_read_bytes']})

def run(pool,name,flags):
 temps=safety();path='/mnt/'+pool+'/'+RUN+'/payload.bin'
 args=['sudo','-n','fio','--name='+name,'--filename='+path,'--size=4G','--ioengine=psync','--iodepth=1','--numjobs=1','--group_reporting','--invalidate=0','--output-format=json']+flags
 emit('test_start',pool=pool,name=name,argv=args,temperatures=temps)
 before=snap();started=time.monotonic();p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 try:
  while True:
   try:out,err=p.communicate(timeout=10);break
   except subprocess.TimeoutExpired:
    if time.monotonic()-started>180:raise RuntimeError('180-second wall timeout')
    safety()
  if p.returncode:raise RuntimeError('fio failed '+str(p.returncode)+': '+err+out[:500])
 except Exception:
  p.terminate()
  try:p.communicate(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.communicate()
  raise
 after=snap();j=json.loads(out);job=j['jobs'][0]
 if job.get('error'):raise RuntimeError('fio job error '+str(job['error']))
 result={'pool':pool,'name':name,'metrics':delta(before,after,POOLS[pool]),'fio':j,'temperatures_after':safety()}
 for direction in ['read','write']:
  r=job[direction]
  if r['io_bytes']:
   result[direction]=dict(bytes=r['io_bytes'],runtime_ms=r['runtime'],MBs=r['bw_bytes']/1e6,MiBs=r['bw_bytes']/2**20,iops=r['iops'],clat_mean_ms=r['clat_ns']['mean']/1e6,clat_p99_ms=r['clat_ns'].get('percentile',{}).get('99.000000',0)/1e6)
 emit('result',**result)
try:
 emit('preflight',pools=cmd(['zpool','list']),version=cmd(['zfs','version']),fio=cmd(['fio','--version']),temperatures=safety(),arc=snap()['arc'])
 b=snap();time.sleep(10);a=snap();emit('baseline10s',metrics={pool:delta(b,a,devs) for pool,devs in POOLS.items()})
 for pool in POOLS:
  name=pool+'/'+RUN
  check=subprocess.run(['zfs','list','-H',name],capture_output=True,text=True)
  if check.returncode==0:raise RuntimeError('Refusing existing dataset '+name)
  config=dict(name=name,type='FILESYSTEM',compression='OFF',atime='OFF',sync='STANDARD',recordsize='128K',quota=8589934592)
  cmd(['midclt','call','pool.dataset.create',json.dumps(config)]);CREATED.append(name)
  cmd(['sudo','-n','zfs','set','primarycache=metadata','secondarycache=none',name])
  emit('dataset_created',name=name,properties=cmd(['zfs','get','-Hp','compression','-r',name]) if False else cmd(['zfs','get','-Hp','compression,sync,recordsize,primarycache,secondarycache,atime,quota,direct',name]))
  run(pool,'sequential-write-flushed',['--rw=write','--bs=1M','--direct=0','--end_fsync=1','--runtime=120'])
  props=cmd(['zfs','list','-Hp','-o','name,used,logicalused,compressratio',name]);emit('allocation',pool=pool,properties=props)
  run(pool,'sequential-read-direct',['--rw=read','--bs=1M','--direct=1','--readonly','--allow_file_create=0','--runtime=90'])
  run(pool,'sequential-read-prefetch-cache-disabled',['--rw=read','--bs=1M','--direct=0','--readonly','--allow_file_create=0','--runtime=90'])
  run(pool,'random-read-4k-disk',['--rw=randread','--bs=4K','--direct=1','--readonly','--allow_file_create=0','--time_based=1','--runtime=15','--randrepeat=1'])
  run(pool,'random-write-4k-fsync-each',['--rw=randwrite','--bs=4K','--direct=0','--allow_file_create=0','--time_based=1','--runtime=10','--fsync=1','--end_fsync=1','--randrepeat=1'])
  cmd(['sudo','-n','zfs','set','primarycache=all',name]);emit('cache_mode',pool=pool,primarycache='all',secondarycache='none')
  run(pool,'sequential-read-arc-warmup',['--rw=read','--bs=1M','--direct=0','--readonly','--allow_file_create=0','--runtime=90'])
  run(pool,'sequential-read-warm-arc',['--rw=read','--bs=1M','--direct=0','--readonly','--allow_file_create=0','--runtime=90'])
  run(pool,'random-read-4k-warm-arc',['--rw=randread','--bs=4K','--direct=0','--readonly','--allow_file_create=0','--time_based=1','--runtime=10','--randrepeat=1'])
  cmd(['midclt','call','pool.dataset.delete',name]);CREATED.remove(name);emit('dataset_deleted',name=name)
 emit('complete',health=cmd(['zpool','status','-x']),temperatures=safety())
except Exception as e:
 emit('error',error=str(e));sys.exitcode=1
finally:
 for name in CREATED[:]:
  try:cmd(['midclt','call','pool.dataset.delete',name]);CREATED.remove(name);emit('cleanup_deleted',name=name)
  except Exception as e:emit('cleanup_error',name=name,error=str(e))
 if getattr(sys,'exitcode',0):sys.exit(1)
