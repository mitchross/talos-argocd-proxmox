import os,sys,json,time,tempfile,pathlib,signal,random,mmap,hashlib,datetime
base=sys.argv[1];size=1024**3;block=1024**2;limit=90
result={'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':base,'sizeBytes':size,'method':'one Python process; QD1; 1 MiB sequential; 128 x 8 KiB write+fsync; O_DIRECT read; unique scratch file'}
def timeout(signum,frame):raise TimeoutError('90 second workload deadline')
def stats():
 p=pathlib.Path('/sys/fs/cgroup/cpu.stat');return p.read_text() if p.exists() else None
def disks():
 return {r[2]:[int(v) for v in r[3:]] for l in pathlib.Path('/proc/diskstats').read_text().splitlines() if len(r:=l.split())>=14}
def pct(xs,p):return sorted(xs)[min(len(xs)-1,int((len(xs)-1)*p))]
folder=None;fd=None;signal.signal(signal.SIGALRM,timeout);signal.alarm(limit)
try:
 if os.statvfs(base).f_bavail*os.statvfs(base).f_frsize < size*3:raise RuntimeError('less than 3 GiB free')
 before=disks();result['cpuBefore']=stats()
 folder=tempfile.mkdtemp(prefix='.capacity-benchmark-20260920-',dir=base);file=folder+'/payload.bin'
 fd=os.open(file,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);buf=os.urandom(block)
 start=time.monotonic()
 for n in range(size//block):
  written=os.write(fd,buf)
  if written!=block:raise RuntimeError('short write')
 buffered=time.monotonic()-start;fs=time.monotonic();os.fsync(fd);flush=time.monotonic()-fs;total=time.monotonic()-start
 result['sequentialWrite']={'MBsIncludingFsync':size/total/1e6,'secondsIncludingFsync':total,'bufferedSeconds':buffered,'finalFsyncSeconds':flush,'bytes':size}
 os.lseek(fd,0,os.SEEK_SET)
 if os.read(fd,block)!=buf:raise RuntimeError('first block readback mismatch')
 rng=random.Random(20260920);samples=[];syncs=[];rnd=os.urandom(8192)
 for _ in range(128):
  os.lseek(fd,rng.randrange(size//8192)*8192,os.SEEK_SET);start=time.monotonic()
  if os.write(fd,rnd)!=8192:raise RuntimeError('short random write')
  fs=time.monotonic();os.fsync(fd);end=time.monotonic();samples.append((end-start)*1000);syncs.append((end-fs)*1000)
 result['randomWriteFsync']={'blockBytes':8192,'operations':len(samples),'cycleMeanMs':sum(samples)/len(samples),'cycleP50Ms':pct(samples,.5),'cycleP95Ms':pct(samples,.95),'cycleP99Ms':pct(samples,.99),'fsyncMeanMs':sum(syncs)/len(syncs),'iops':1000/(sum(samples)/len(samples))}
 os.close(fd);fd=None
 try:
  fd=os.open(file,os.O_RDONLY|os.O_DIRECT);b=mmap.mmap(-1,block);start=time.monotonic();count=0
  while count<size:
   n=os.readv(fd,[b])
   if n<=0:raise RuntimeError('short direct read')
   count+=n
  elapsed=time.monotonic()-start
  result['sequentialReadDirect']={'MBs':count/elapsed/1e6,'seconds':elapsed,'bytes':count,'meaning':'bypasses guest/client page cache; upstream caches may serve data'}
  start=time.monotonic();lat=[]
  for _ in range(256):
   os.lseek(fd,rng.randrange(size//4096)*4096,os.SEEK_SET);t=time.monotonic();n=os.readv(fd,[memoryview(b)[:4096]]);lat.append((time.monotonic()-t)*1000)
   if n!=4096:raise RuntimeError('short random read')
  elapsed=time.monotonic()-start
  result['randomReadDirect']={'blockBytes':4096,'operations':len(lat),'iops':len(lat)/elapsed,'p50Ms':pct(lat,.5),'p95Ms':pct(lat,.95),'p99Ms':pct(lat,.99),'meaning':'short path-latency sample, not uncached physical-disk IOPS'}
  b.close();os.close(fd);fd=None
 except OSError as e:
  result['directReadUnavailable']=str(e)
  if fd is not None:os.close(fd);fd=None
 after=disks();result['diskDelta']={d:{'readBytes':(after[d][2]-v[2])*512,'writeBytes':(after[d][6]-v[6])*512} for d,v in before.items() if d in after and (after[d][2]!=v[2] or after[d][6]!=v[6])};result['cpuAfter']=stats()
except Exception as e:result['error']=str(e)
finally:
 signal.alarm(0)
 if fd is not None:os.close(fd)
 if folder:
  try:os.unlink(folder+'/payload.bin');os.rmdir(folder);result['cleanup']='removed exact scratch file and directory'
  except Exception as e:result['cleanupError']=str(e)
 result['finishedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat();print(json.dumps(result))
