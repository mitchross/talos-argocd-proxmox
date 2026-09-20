import os,tempfile,time,json,random,signal,shutil,datetime,statistics

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def diskstats():
 return {v[2]:[int(x) for x in v[3:]] for v in (l.split() for l in open('/proc/diskstats')) if not v[2].startswith(('loop','dm-'))}
def cpu():return [int(x) for x in open('/proc/stat').readline().split()[1:]]
def counters(before,after,seconds):
 rows={}
 for k,b in before.items():
  if k not in after:continue
  d=[x-y for x,y in zip(after[k],b)]
  if d[0] or d[4]:rows[k]={'read_bytes':d[2]*512,'write_bytes':d[6]*512,'read_iops':d[0]/seconds,'write_iops':d[4]/seconds,'busy_pct':100*d[9]/(seconds*1000)}
 return rows

def alarm(*_):raise TimeoutError('120-second total benchmark deadline exceeded')
signal.signal(signal.SIGALRM,alarm);signal.alarm(120)
root=None;fd=None;result={'started_at':stamp(),'scope':'Proxmox root filesystem scratch file, not guest VM storage tier','dataset_bytes':1024**3,'tests':[],'errors':[],'cleanup':False}
try:
 stat=os.statvfs('/var/lib/vz');assert stat.f_bavail*stat.f_frsize>5*1024**3,'insufficient root free space'
 root=tempfile.mkdtemp(prefix='agent-bench-20260920-',dir='/var/lib/vz');result['scratch_directory']=root
 fd=os.open(root+'/payload.bin',os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);block=os.urandom(1024**2)
 def record(name,fn,totalbytes):
  b=diskstats();bcpu=cpu();start=time.perf_counter();extra=fn();seconds=time.perf_counter()-start;a=diskstats();dc=[x-y for x,y in zip(cpu(),bcpu)];ct=sum(dc[:8]);r={'name':name,'finished_at':stamp(),'seconds':seconds,'bytes':totalbytes,'MBs':totalbytes/1e6/seconds,'physical_disk_counters':counters(b,a,seconds),'cpu_busy_pct':100*(ct-dc[3]-dc[4])/ct,'cpu_iowait_pct':100*dc[4]/ct}
  if extra:r.update(extra)
  result['tests'].append(r)
 def write():
  for i in range(1024):
   n=os.write(fd,block);assert n==len(block)
   if (i+1)%64==0:
    os.fsync(fd)
    if hasattr(os,'posix_fadvise'):os.posix_fadvise(fd,i*1024**2-63*1024**2,64*1024**2,os.POSIX_FADV_DONTNEED)
  os.fsync(fd)
 record('sequential-write-1GiB-fsync-every-64MiB-and-final',write,1024**3)
 if hasattr(os,'posix_fadvise'):
  os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED);result['read_cache_control']='per-file POSIX_FADV_DONTNEED after fsync; advisory, not proof of eviction'
 else:result['read_cache_control']='none; cache may affect reads'
 def read():
  os.lseek(fd,0,os.SEEK_SET);n=0
  while True:
   b=os.read(fd,1024**2)
   if not b:break
   n+=len(b)
   if n%(64*1024**2)==0 and hasattr(os,'posix_fadvise'):os.posix_fadvise(fd,n-64*1024**2,64*1024**2,os.POSIX_FADV_DONTNEED)
  assert n==1024**3
 record('sequential-read-1GiB-after-cache-eviction-hint',read,1024**3)
 latencies=[];rng=random.Random(20260920);small=os.urandom(8192)
 def syncwrites():
  for i in range(128):
   offset=rng.randrange(0,1024**3//8192)*8192;st=time.perf_counter();n=os.pwrite(fd,small,offset);assert n==len(small);os.fsync(fd);latencies.append((time.perf_counter()-st)*1000)
  times=sorted(latencies)
  return {'operations':128,'p50_ms':statistics.median(times),'p95_ms':times[121],'p99_ms':times[126],'max_ms':times[-1],'latency_scope':'8KiB write plus fsync syscall elapsed time'}
 record('random-write-8KiB-fsync-each',syncwrites,128*8192)
except Exception as e:result['errors'].append(type(e).__name__+': '+str(e))
finally:
 signal.alarm(0)
 if fd is not None:os.close(fd)
 if root:
  shutil.rmtree(root);result['cleanup']=not os.path.exists(root)
 result['finished_at']=stamp();print(json.dumps(result,indent=2))
