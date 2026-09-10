'use strict';
(async () => {
  let D;
  try {
    const response = await fetch('inventory.json', {cache: 'no-cache'});
    if (!response.ok) throw new Error(`Inventory HTTP ${response.status}`);
    D = await response.json();
  } catch (error) {
    document.querySelector('#inspection-panel').textContent = `The inspection inventory could not be loaded: ${error.message}. Open this report through the documentation web server.`;
    return;
  }
  const list = k => Array.isArray(D[k]) ? D[k] : [];
  const hosts = list('hosts'), disks = list('disks'), nodes = list('nodes');
  const workloads = list('workloads').length ? list('workloads') : list('healthWorkloads');
  const pvcs = list('pvcs').length ? list('pvcs') : list('pvc');
  const panel = document.querySelector('#inspection-panel');
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = value => { const parsed=new Date(value); return value && Number.isFinite(parsed.getTime()) ? `${parsed.toLocaleString('en-US',{month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'UTC'})} UTC` : value || 'Not collected'; };
  const num = (v, digits = 1) => v == null || !Number.isFinite(Number(v)) ? 'Not collected' : Number(v).toLocaleString('en-US', {maximumFractionDigits:digits});
  const latency = v => v==null?'Not observed':`${num(v,3)} ms`;
  const pct = v => v == null ? 'Not collected' : `${num(v)}%`;
  const bytes = v => v == null ? 'Not collected' : `${num(v / 1e9,0)} GB`;
  const gib = v => v == null ? 'Not collected' : `${num(v,2)} GiB`;
  const memory = v => { if(v == null) return 'No allocation'; const m=String(v).match(/^([0-9.]+)(Ki|Mi|Gi|Ti)?$/); if(!m) return String(v); return gib(Number(m[1]) * ({Ki:2**10,Mi:2**20,Gi:2**30,Ti:2**40}[m[2]] || 1) / 2**30); };
  const badge = (text, tone='neutral') => `<span class="badge ${tone}">${esc(text)}</span>`;
  const title = (a,b) => `<span class="cell-title">${esc(a)}</span>${b ? `<span class="cell-sub">${esc(b)}</span>` : ''}`;
  const small = s => `<span class="small">${esc(s)}</span>`;
  const tone = s => /critical|danger|failed|degraded|replace|upgrade first|crash|faulted/i.test(s || '') ? 'danger' : /warn|medium|investigate|watch|plan|pending|unknown|review|slow|outofsync/i.test(s || '') ? 'warning' : /healthy|synced|keep|succeeded|ready|verified|passed/i.test(s || '') ? 'good' : 'neutral';
  const shortNode = s => String(s || '').replace('talos-prod-cluster-v2-','').replace(/-(workers|planes)-[a-z0-9]+$/,'').replace('control','control plane');
  const hostName = id => hosts.find(h => h.id === id)?.name || id;
  const join = x => Array.isArray(x) ? x.join(', ') : x;
  const evidenceText = x => Array.isArray(x) ? x.join(' · ') : x && typeof x === 'object' ? JSON.stringify(x) : x;
  const head = (number,label,copy) => `<div class="section-heading"><div><p class="eyebrow">INSPECTION ${number} / 07</p><h2>${esc(label)}</h2><p>${esc(copy)}</p></div><span class="section-number">SERVICE RECORD / ${number}</span></div>`;
  const callout = (label,copy,level='warning') => `<div class="callout ${level}"><h3>${esc(label)}</h3><p>${esc(copy)}</p></div>`;
  const metric = (label,value,copy) => `<div class="metric-card"><span class="label">${esc(label)}</span><strong>${esc(value)}</strong><p>${esc(copy)}</p></div>`;
  function table(target, rows, columns, {placeholder='Search this inventory…', options=null, filter=null}={}) {
    const root = document.createElement('div');
    root.innerHTML = `<div class="toolbar"><input type="search" aria-label="${esc(placeholder)}" placeholder="${esc(placeholder)}">${options ? `<label>Show <select aria-label="Filter inventory">${options.map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('')}</select></label>` : ''}<span class="result-count" role="status"></span></div><div class="table-wrap" role="region" aria-label="Searchable inspection inventory" tabindex="0"><table><thead><tr>${columns.map(c=>`<th scope="col">${esc(c[0])}</th>`).join('')}</tr></thead><tbody></tbody></table></div>`;
    target.append(root);
    const input=root.querySelector('input'), select=root.querySelector('select'), body=root.querySelector('tbody');
    function draw() {
      const query=input.value.toLowerCase().trim();
      const found=rows.filter(r=>(!query || JSON.stringify(r).toLowerCase().includes(query)) && (!filter || filter(r,select?.value)));
      body.innerHTML=found.length ? found.map(r=>`<tr>${columns.map(c=>`<td>${c[1](r)}</td>`).join('')}</tr>`).join('') : `<tr><td class="empty" colspan="${columns.length}">${rows.length ? 'No records match these filters. Clear the search or choose another view.' : 'This data was not included in the recorded inspection.'}</td></tr>`;
      root.querySelector('.result-count').textContent=`${found.length} of ${rows.length} records`;
    }
    input.addEventListener('input',draw); select?.addEventListener('change',draw); draw(); return root;
  }
  const bar = v => `<div class="bar ${v>80?'warn':''}"><span style="width:${Math.max(0,Math.min(100,Number(v)||0))}%"></span></div>`;
  const section = html => { const x=document.createElement('div');x.innerHTML=html;panel.append(x);return x; };
  const bullets = values => `<ul class="detail-list">${(values || []).map(value => `<li>${esc(value)}</li>`).join('')}</ul>`;
  const priorityTone = priority => priority === 'P1' || priority === 'P2' ? 'warning' : 'good';
  const dated = key => `<p class="capture-note">Table / chart evidence: ${esc(date(D.datasetDates?.[key] || D.baselineAt || D.collectedAt))}. Latest reinspection is summarized above; older rows are historical where no replacement capture is available.</p>`;
  function recheck(key) {
    const item = D.reinspection?.[key];
    if (!item) return callout('Latest reinspection pending', 'The detailed baseline below is historical. This section has no newer verified capture in this inventory; do not interpret it as current cluster health.');
    return `<article class="recheck ${esc(item.status || 'neutral')}"><div class="card-meta">${badge(item.label || 'Reinspection', item.status || 'neutral')}<span class="small">Checked ${esc(date(item.checkedAt || D.reinspection.checkedAt))}</span></div><h3>${esc(item.summary)}</h3>${bullets(item.evidence)}${item.limitations ? `<p class="small">${esc(item.limitations)}</p>` : ''}</article>`;
  }
  function renderDisks() {
    panel.innerHTML=head('01','Start at the disks.','Click any drive for its decision, urgency, evidence, replacement constraints and complete path to the workload.') + recheck('disks') + callout('A recommendation is not a failure diagnosis.','P1 = investigate promptly. P2 = plan maintenance or improve resilience. P3 = keep and monitor. No recorded SMART pass proves durability, and the repaired read storm is not grounds by itself to replace the SSD.','good') + dated('disks');
    const chips=section('<div class="host-chips" aria-label="Filter disks by physical host"></div>').firstElementChild;
    const summary=section(''), inventory=section(''); let selected='all';
    const choices=[{id:'all',name:'All hosts'},...hosts];
    choices.forEach(h=>{const b=document.createElement('button');b.className='host-chip';b.dataset.host=h.id;b.innerHTML=`${esc(h.name)} <span class="count">${h.id==='all'?disks.length:disks.filter(d=>d.host===h.id).length}</span>`;b.addEventListener('click',()=>{selected=h.id;draw();});chips.append(b);});
    function draw(){
      chips.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.host===selected)));
      const h=hosts.find(h=>h.id===selected);
      summary.innerHTML=h?`<div class="host-summary"><div><span class="label">Physical host · ${esc(h.ip)}</span><h3>${esc(h.name)}</h3><p>${esc(h.role)}</p><p>${esc(h.model)}${h.board ? ` / ${esc(h.board)}`:''}</p></div><div><span class="label">Processor & memory</span><p>${esc(h.cpu)}</p><p>${num(h.logicalCpus,0)} logical CPUs · ${num(h.ramGiB)} GiB RAM</p><p>${num(h.availableGiB)} GiB available at latest capture</p></div><div><span class="label">Guest mapping · baseline</span><p>Talos: ${esc(h.nodeIps)}</p><p>${(h.vms||[]).map(v=>`${esc(v.kind)} ${esc(v.id)} · ${esc(v.state)} · ${num(v.ramMiB/1024)} GiB`).join('<br>') || 'No guest VMs in this inventory'}</p></div></div>`:'';
      inventory.replaceChildren();
      table(inventory,disks.filter(d=>selected==='all'||d.host===selected),[
        ['Drive / host',d=>`<button class="disk-link" data-disk="${esc(d.id)}">${esc(d.model)} ↗</button><span class="cell-sub">${esc(hostName(d.host))} · /dev/${esc(d.device)}</span><span class="cell-sub">${esc(date(d.checkedAt || 'No fresh capture'))}</span>`],
        ['Capacity / role',d=>title(bytes(d.bytes),d.role)],
        ['SMART',d=>badge(d.observationStatus==='unavailable'?'Unavailable':d.smart?.passed===true?'Passed':d.smart?.passed===false?'Failed':'Not reported',d.smart?.passed===true?'good':d.smart?.passed===false?'danger':'neutral')],
        ['Temperature / use',d=>title(d.smart?.tempC==null?'Temp not collected':`${num(d.smart.tempC,0)} °C`,d.smart?.enduranceUsedPct==null?'Endurance not reported':`${num(d.smart.enduranceUsedPct,0)}% endurance used`)],
        ['Latest passive I/O',d=>title(d.sample?`${num(d.sample.busyPct)}% busy`:'Not collected',d.sample?`Read ${latency(d.sample.readMs)} · Write ${latency(d.sample.writeMs)}`:'')],
        ['Inspection decision',d=>`${badge(`${d.assessment.priority} · ${d.action}`,priorityTone(d.assessment.priority))}<span class="cell-sub">${esc(d.assessment.reason)}</span>`]
      ],{placeholder:'Search model, host, device, role or path…'});
    }
    inventory.addEventListener('click',e=>{const b=e.target.closest('[data-disk]');if(b)showDisk(b.dataset.disk);});draw();
    section('<p class="body-copy">Click a drive for its complete storage path and evidence. “Not reported” means the device or collector did not expose a value; it does not mean zero errors. GB is decimal capacity; VM allocations and memory use GiB.</p>');
    if(D.physical?.nas?.pools?.length){
      section('<h3 class="subheading">NAS pools and durability</h3><p class="capture-note">Checked '+esc(date(D.physical.nas.checkedAt))+'</p>');
      table(panel,D.physical.nas.pools,[['Pool',p=>title(p.name,D.physical.nas.topology[p.name])],['Health',p=>badge(p.health,p.health==='ONLINE'?'good':'warning')],['Allocated',p=>`${pct(p.allocatedPct)}${bar(p.allocatedPct)}`],['Free space',p=>esc(bytes(p.freeBytes))]],{placeholder:'Search NAS pool or redundancy…'});
      section(callout('Pool health and synchronous-write durability are different.','BigTank/k8s still has sync disabled, inherited by its NFS/iSCSI descendants. BigTank/k8s/rustfs overrides standard. AI-pool remains a three-drive stripe and Backup10T a single-disk pool. An ONLINE pool does not remove those failure boundaries.'));
    }

  }
  function showDisk(id){
    const d=disks.find(d=>d.id===id);if(!d)return;
    const s=d.smart||{},io=d.sample;
    const values=[['Capacity',bytes(d.bytes)],['Temperature',s.tempC==null?'Not reported':`${num(s.tempC,0)} °C`],['Power-on hours',num(s.hours,0)],['Endurance consumed',s.enduranceUsedPct==null?'Not reported':`${num(s.enduranceUsedPct,0)}%`],['Available spare',s.sparePct==null?'Not reported':`${num(s.sparePct,0)}%`],['Media errors',num(s.mediaErrors,0)],['Reallocated sectors',num(s.reallocated,0)],['CRC errors',num(s.crcErrors,0)],['Unsafe shutdowns',num(s.unsafeShutdowns,0)],['Error-log entries',num(s.errorLogEntries,0)],['Grown defects',num(s.grownDefects,0)],['SMART overall',s.passed===true?'Passed':s.passed===false?'Failed':'Not reported']];
    const a=d.assessment || {};
    const ioGrid = sample => `<div class="detail-grid">${[['Busy',pct(sample.busyPct)],['Average read',latency(sample.readMs)],['Average write',latency(sample.writeMs)],['Average queue',num(sample.queue,3)],['Read IOPS',num(sample.readIops)],['Write IOPS',num(sample.writeIops)],['Write throughput',`${num(sample.writeMiBs,3)} MiB/s`]].map(([k,v])=>`<div class="detail-stat"><span class="label">${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div>`;
    document.querySelector('#detail-content').innerHTML=`<h2 id="detail-title">${esc(d.model)}</h2><p class="body-copy">${esc(hostName(d.host))} · /dev/${esc(d.device)} · ${esc(d.role)}</p><div class="decision-lead">${badge(`${a.priority} · ${a.verdict}`,priorityTone(a.priority))}<h3>${esc(a.reason)}</h3><p>${esc(a.priority==='P1'?'Investigate promptly; confirm the cause before buying hardware.':a.priority==='P2'?'Plan the work; the evidence does not establish an emergency drive failure.':'Keep in service and trend the relevant health signals.')}</p></div><h3 class="subheading">Why this decision</h3>${bullets(a.evidence)}<p class="capture-note">Decision evidence checked ${esc(date(a.checkedAt))}. ${esc(a.confidence)}</p><h3 class="subheading">What depends on it</h3><p class="body-copy">${esc(a.impact)}</p><p class="capture-note">VM / mount mapping checked ${esc(date(d.mappingCheckedAt || D.hardwareCheckedAt))}; the current drive identity check does not revalidate every guest mount.</p><div class="detail-flow">${String(d.path||'Path not collected').split('→').map(p=>`<span>${esc(p.trim())}</span>`).join('')}</div><div class="grid-two"><section class="explain-card"><h3>Options</h3>${bullets(a.options)}</section><section class="explain-card"><h3>Before you swap anything</h3>${bullets(a.constraints)}</section></div>${d.repairSamples?.length?`<h3 class="subheading">Repair verification on this physical path</h3><div class="table-wrap"><table><thead><tr><th>Window</th><th>Reads</th><th>Queue</th><th>Average read</th></tr></thead><tbody>${d.repairSamples.map(r=>`<tr><td>${title(r.label,date(r.at))}</td><td>${num(r.readMiBs,2)} MiB/s</td><td>${num(r.queue,3)}</td><td>${r.readMs==null?'Not recorded':`${num(r.readMs,3)} ms`}</td></tr>`).join('')}</tbody></table></div><p class="body-copy">Workload intensity varied; one window includes a normal backup. The quietest window is not a permanent baseline.</p>`:''}<h3 class="subheading">Latest hardware health</h3><p class="capture-note">${esc(date(d.checkedAt || d.unavailableReason || 'No fresh capture'))}</p><div class="detail-grid">${values.map(([k,v])=>`<div class="detail-stat"><span class="label">${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div><h3 class="subheading">Latest ${num(d.sampleSeconds,0)}-second passive I/O</h3><p class="capture-note">${esc(date(d.sampleStartedAt || 'Not collected'))} → ${esc(date(d.sampleEndedAt || 'Not collected'))}</p>${io?ioGrid(io):'<p class="body-copy">No timed I/O sample was captured for this device.</p>'}<p><a class="button" href="https://grafana.vanillax.me/d/homelab-diagnostics?viewPanel=${1000+disks.indexOf(d)}">Open this drive in Grafana ↗</a></p><h3 class="subheading">Pass the next inspection</h3>${bullets(a.verify)}<p class="body-copy">Historical totals are not current failure rates. A disk change requires a reviewed migration and recovery plan.</p>`;
    history.replaceState(null,'',`#drive-${encodeURIComponent(id)}`);
    document.querySelector('#detail-dialog').showModal();
  }

  function renderResources(){
    panel.innerHTML=head('02','Memory, CPU & the VPA.','Requests reserve scheduler capacity. Limits still constrain a container when the host has free RAM; RequestsOnly VPA policies cannot raise those fixed limits.') + recheck('resources') + dated('resources');
    renderAllocationCharts();
    table(panel,nodes,[['Talos node',n=>title(shortNode(n.node),`${n.ip} · ${n.ready==='True'?'Ready':n.ready==='Unknown'?'Status unknown':n.ready || 'Not recorded'} · ${n.pods} pods`)],['Container CPU / allocatable',n=>`${pct(n.cpu_exec)}${bar(n.cpu_exec)}`],['I/O wait / steal',n=>title(`${pct(n.cpu_iowait)} / ${pct(n.cpu_steal)}`,'Steal = time withheld by hypervisor')],['CPU reserved',n=>`${pct(n.cpu_request_pct)}${bar(n.cpu_request_pct)}`],['Container RAM',n=>title(gib(n.container_memory_usage_gib),`${gib(n.memory_allocatable_gib)} allocatable`)],['RAM reserved',n=>`${pct(n.memory_request_pct)}${bar(n.memory_request_pct)}`]],{placeholder:'Search Talos node, address or pool…'});
    section(dated('hosts')+'<h3 class="subheading">Physical host memory & DIMMs</h3><p class="body-copy">Host available memory and container working sets are different measurements. Kernel memory and load were rechecked; DIMM identity and negotiated speeds retain the baseline inventory date.</p>');
    table(panel,hosts,[['Host',h=>title(h.name,`${h.cpu} · ${date(h.resourcesCheckedAt)}`)],['Kernel RAM / available',h=>title(`${num(h.ramGiB)} / ${num(h.availableGiB)} GiB`,`${num(h.logicalCpus,0)} logical CPUs`)],['Load · 1 / 5 / 15 min',h=>title((h.load||[]).map(x=>num(x,2)).join(' / '),'Task demand, not CPU utilization')],['Installed DIMMs · baseline',h=>esc((h.dimms||[]).map(d=>`${d.Size} ${d.Type} @ ${d['Configured Memory Speed']}`).join('; ')||'Soldered or not reported')]],{placeholder:'Search physical host, CPU or memory…'});
    section('<h3 class="subheading">Current VPA recommendations</h3><p class="body-copy">Each row is a recommended container. A target is not proof that every pod already received it. The aggregate updater/admission counters above demonstrate that VPA is doing work.</p>'+dated('vpa'));
    table(panel,list('vpa'),[['Policy / container',v=>title(`${v.namespace}/${v.vpa}`,v.container)],['Update mode',v=>esc(v.mode)],['Recommended target',v=>title(`${num(v.target?.cpu,3)} CPU`,gib(v.target?.memory_gib))],['Lower bound',v=>title(v.lowerBound?.cpu,memory(v.lowerBound?.memory))],['Upper bound',v=>title(v.upperBound?.cpu,memory(v.upperBound?.memory))]],{placeholder:'Search VPA policy, container or update mode…'});

  }
  function renderAllocationCharts(){
    const chart=(heading,usageKey,requestKey,totalKey,unit)=>`<figure class="allocation-chart"><figcaption><strong>${esc(heading)}</strong><span>Each node = 100% allocatable</span></figcaption><div class="chart-legend"><span class="legend-used">Observed use</span><span class="legend-requested">Requested (if collected)</span></div>${nodes.map(n=>{
      const total=Number(n[totalKey]),used=n[usageKey],requested=n[requestKey];
      const width=v=>v==null?0:Math.max(0,Math.min(100,100*v/total));
      return `<div class="allocation-row"><div class="allocation-label"><strong>${esc(shortNode(n.node))}</strong><span>${num(used,2)} used / ${num(requested,2)} requested / ${num(total,2)} ${unit}</span></div><div class="allocation-tracks" role="img" aria-label="${esc(shortNode(n.node))}: observed ${num(used==null?null:100*used/total)} percent; requested ${num(requested==null?null:100*requested/total)} percent of allocatable"><div><span class="used" style="width:${width(used)}%"></span></div><div><span class="requested" style="width:${width(requested)}%"></span></div></div>`;
    }).join('')}</figure>`;
    section(`<div class="grid-two">${chart('CPU: use and reservation','container_cpu_usage','cpu_requests','cpu_allocatable','cores')}${chart('Memory: use and reservation','container_memory_usage_gib','memory_requests_gib','memory_allocatable_gib','GiB')}</div><p class="body-copy">Paired bars are separate measurements, not additive. Memory use is container working set; requests are scheduler reservations. Host caches and kernel memory are outside this container view. ${esc(D.requestMetricScope)}</p>`);
  }
  function renderSpread(){
    const active=workloads.filter(w=>w.desired>0&&w.kind!=='DaemonSet');
    panel.innerHTML=head('03','Spread the failure domains.','Count independent physical hosts and surviving data copies. A second frontend does not remove its database, broker or storage dependency.') + recheck('spread') + dated('spread') + `<div class="metric-grid">${metric('Active deployments / sets',active.length,'Recorded rows; DaemonSets and parked workloads excluded.')}${metric('Single-replica workloads',active.filter(w=>w.desired===1).length,'One instance in the recorded configuration.')}${metric('PVCs with multiple copies',pvcs.filter(p=>p.longhorn_desired_replicas>1).length,'Configured Longhorn targets, not backup copies.')}${metric('Failure domains','Physical hosts','Several replicas on one host can fail together.')}</div>`;
    table(panel,workloads,[['Workload',w=>title(`${w.namespace}/${w.workload}`,w.kind)],['Ready / desired',w=>badge(`${w.ready} / ${w.desired}`,w.ready<w.desired?'danger':w.desired===0?'neutral':'good')],['Physical hosts',w=>esc(join(w.replica_physical_hosts)||'No running pod')],['Placement constraints',w=>title(w.topology_spread==null?'Not collected':w.topology_spread?'Topology spread (baseline policy)':'No spread constraint (baseline policy)',w.pod_anti_affinity==null?'Policy not collected':w.pod_anti_affinity?'Pod anti-affinity present (baseline)':'No pod anti-affinity (baseline)')],['Storage / rollout',w=>title(w.strategy||'Not applicable',w.rwo_pvcs?.length?`${w.rwo_pvcs.length} RWO claims`:'No directly referenced RWO PVC')]],{placeholder:'Search workload, physical host or claim…',options:[['active','Active workloads'],['all','Include parked'],['single','Single replica'],['multi','Multiple replicas']],filter:(w,f)=>f==='all'||f==='single'&&w.desired===1||f==='multi'&&w.desired>1||f==='active'&&w.desired>0});
    section('<h3 class="subheading">Persistent volume placement</h3><p class="body-copy">Healthy means the configured target is met. Replica objects can include stopped or failed remnants; the inventory retains their individual states and disk paths.</p>');
    table(panel,pvcs,[['Claim',p=>title(`${p.namespace}/${p.pvc}`,p.requested_size)],['Storage',p=>title(p.storage_class,join(p.access_modes))],['Configured / running copies',p=>title(p.longhorn_desired_replicas==null?'Not Longhorn':`${p.longhorn_desired_replicas} / ${p.running_nonfailed_replica_count}`,p.longhorn_robustness)],['Replica hosts',p=>esc(join(p.replica_physical_hosts)||'Not recorded')],['Disk paths',p=>esc([...new Set((p.replica_objects||[]).map(r=>r.disk_path))].join(', ')||'Not Longhorn')]],{placeholder:'Search PVC, replica host or disk path…'});
  }
  function renderThrash(){
    panel.innerHTML=head('04','Repair the cause. Measure again.','Temporal and DCGM were repaired through PR 2307. The old 128 MiB / 512 MiB limits are incident history, not the current deployed configuration.') + recheck('thrashing');
    section(`<div class="repair-list">${list('repairs').map(r=>`<article class="repair-card"><div class="card-meta">${badge(r.state,/ongoing|pending/i.test(r.state)?'warning':'good')}<a href="https://github.com/mitchross/talos-argocd-proxmox/pull/${Number(r.pr)}">PR #${Number(r.pr)}</a></div><h3>${esc(r.name)}</h3><span class="label">Before</span><p>${esc(r.before)}</p><span class="label">After</span><p>${esc(r.after)}</p><p class="small">Verified ${esc(date(r.checkedAt))}</p></article>`).join('')}</div>`);
    section(`<h3 class="subheading">Same storage path, before and after repair</h3><div class="metric-grid">${metric('Physical queue','527 → 0.085','Quiet 30-second window; later samples 8.128 and 1.617.')}${metric('Reads','732 → 1.65 MiB/s','Before / quiet post-repair sample, September 9 UTC.')}${metric('PVC fsync p99','172 → 13.7 ms','Same bounded TubeSync PVC probe; 100 samples.')}${metric('Temporal runtime','25 h → 4 s','Initial recovery and latest 21:55 UTC run both verified.')}</div><p class="body-copy">These are dated repair measurements, not live counters or proof that the SSD can never stall. The next inspection must compare similar workload and backup conditions. Cumulative reads do not consume flash write endurance in the same way as writes.</p>`);
    renderBenchmarks();
  }
  function renderBenchmarks(){
    const samples=list('benchmarks');
    section(dated('benchmarks'));
    section('<h3 class="subheading">Latency measured along the storage paths</h3><p class="body-copy">These small probes measure response latency under the conditions of this inspection. They are not maximum-throughput tests, a sustained-load qualification, or a promise of future performance. The physical disk averages above and the path-probe percentiles below measure different operations.</p>'+callout('Fast acknowledgements need the same durability contract to be comparable.','The SMB path has sync disabled. A fast fsync response on that path is not equivalent to a durable commit on storage that honors synchronous writes. Compare the path, operation and durability note before ranking the results.'));
    const valid=samples.filter(b=>b.p99Ms!=null&&Number.isFinite(Number(b.p99Ms))&&Number(b.p99Ms)>=0),max=Math.max(1,...valid.map(b=>Number(b.p99Ms)));
    if(valid.length){
      section(`<figure class="latency-chart"><figcaption><strong>Tail latency · p99</strong><span>Milliseconds · linear scale · lower is faster</span></figcaption>${valid.map(b=>`<div class="latency-row"><span class="latency-name">${esc(b.name)}</span><div class="latency-track" aria-hidden="true"><span style="width:${Math.max(0,Math.min(100,Number(b.p99Ms)/max*100))}%"></span></div><strong>${num(b.p99Ms,2)} ms</strong></div>`).join('')}<p class="small">Different durability settings prevent a like-for-like performance ranking. Full conditions are listed below.</p></figure>`);
    }
    table(panel,samples,[['Probe / path',b=>title(b.name,b.path)],['p50',b=>esc(b.p50Ms==null?'Not collected':`${num(b.p50Ms,3)} ms`)],['p95',b=>esc(b.p95Ms==null?'Not collected':`${num(b.p95Ms,3)} ms`)],['p99',b=>esc(b.p99Ms==null?'Not collected':`${num(b.p99Ms,3)} ms`)],['Durability contract',b=>esc(evidenceText(b.durability)||'Not specified')],['Interpretation',b=>esc(b.note||'Recorded latency probe; no sustained-load qualification')]],{placeholder:'Search probe, storage path or durability…'});
  }
  function renderArgo(){
    const apps=list('apps'),healthy=apps.filter(a=>a.health==='Healthy').length,synced=apps.filter(a=>a.sync==='Synced').length;
    panel.innerHTML=head('05','GitOps is the service book.','Argo CD can prove that declared resources match Git. It cannot prove that Redis can load its data, backups can read every file, or a queue worker is completing work.')+`<div class="metric-grid">${metric('Applications',apps.length,'All collected Argo CD application records.')}${metric('Healthy',healthy,'Controller health classification at capture.')}${metric('Synced',synced,'Matches the declared state at capture.')}${metric('Operational proof','Separate','Use storage, workload and backup evidence too.')}</div>`;
    section(recheck('argo') + dated('apps'));
    table(panel,apps,[['Argo CD application',a=>title(a.name,a.namespace)],['Health',a=>badge(a.health,tone(a.health))],['Sync',a=>badge(a.sync,tone(a.sync))]],{placeholder:'Search all Argo applications…',options:[['all','All applications'],['attention','Needs attention'],['healthy','Healthy + Synced']],filter:(a,f)=>f==='all'||f==='attention'&&(a.health!=='Healthy'||a.sync!=='Synced')||f==='healthy'&&a.health==='Healthy'&&a.sync==='Synced'});
    section(callout('Treat “green” as one layer of evidence.','A Ready frontend can coexist with a failed Redis dependency or backup. Check a representative service operation and the latest completed backup, not just readiness and schedule status.'));
    section('<div class="grid-two"><div class="explain-card"><h3>Focused Argo improvements</h3><p>Review broad diff exceptions field by field, test shared Kustomize component changes against affected apps, and keep dependency retries bounded. ApplicationSet creation waves are not complete child-service health gates.</p><p>Review the remaining database ApplicationSet selfHeal exception against its current support-service scope. Keep immutable restore exceptions that still have a verified purpose.</p></div><div class="explain-card"><h3>Monitoring that earns its place</h3><p>Keep the trusted Prometheus/Grafana view and one useful log path. Coroot needs a used diagnostic capability and real Keeper failure domains. Keep needs dependable alert delivery.</p><p>At the September 8 baseline, Tempo had received no trace batches and used about 35 MiB. Recheck actual usage before retiring it; choose a traced workflow that provides operational value.</p></div></div>');
    renderNamespaceCosts();
  }
  function renderNamespaceCosts(){
    section(dated('namespaceCosts'));
    const costs=[...list('namespaceCosts')].sort((a,b)=>(Number(b.memoryGiB)||0)-(Number(a.memoryGiB)||0));
    section('<h3 class="subheading">Application & monitoring footprint</h3><p class="body-copy">Observed CPU and memory consumption, grouped by namespace and ordered by memory. This is resource footprint, not a financial bill. High usage alone does not prove waste: compare service value, duplicate collection, retention and operational dependencies before retiring a component.</p>');
    const top=costs.slice(0,8),maximum=Math.max(...top.map(n=>Number(n.memoryGiB)||0),1);
    section(`<figure class="latency-chart footprint-chart"><figcaption><strong>Largest namespace working sets</strong><span>GiB · common linear scale · recorded usage</span></figcaption>${top.map(n=>`<div class="latency-row"><span class="latency-name">${esc(n.namespace)}</span><div class="latency-track" role="img" aria-label="${esc(n.namespace)} ${num(n.memoryGiB,2)} GiB"><span style="width:${100*Number(n.memoryGiB)/maximum}%"></span></div><strong>${num(n.memoryGiB,2)} GiB</strong></div>`).join('')}</figure>`);
    table(panel,costs,[['Namespace',n=>title(n.namespace)],['Observed CPU',n=>esc(n.cpuCores==null?'Not collected':`${num(n.cpuCores,3)} cores`)],['Observed memory',n=>esc(gib(n.memoryGiB))],['Review / next step',n=>title(evidenceText(n.advice)||'Compare operational value and current usage',n.advice?'Advice from baseline inspection':'')]],{placeholder:'Search application, monitoring service or review advice…'});
  }
  function renderHealth(){
    panel.innerHTML=head('06','Health includes recovery.','Inspect failing pods, the services behind them, and the latest completed backups. An old success is not proof of current recovery coverage.') + recheck('health') + dated('workloads');
    table(panel,workloads.filter(w=>w.desired>0),[['Workload',w=>title(`${w.namespace}/${w.workload}`,w.kind)],['Ready / desired',w=>badge(`${w.ready} / ${w.desired}`,w.ready<w.desired?'danger':'good')],['Hosts',w=>esc(join(w.replica_physical_hosts)||'Not recorded')]],{placeholder:'Search workload health…',options:[['attention','Needs attention'],['all','All active workloads']],filter:(w,f)=>f==='all'||w.ready<w.desired});
    section('<h3 class="subheading">Backup and restore evidence</h3>'+dated('pvcs'));
    table(panel,pvcs,[['Claim',p=>title(`${p.namespace}/${p.pvc}`,p.storage_class)],['Backup contract',p=>p.backup_policy?badge('Policy present','good'):p.backup_exempt==='true'?badge('Explicit exemption','neutral'):badge('Unclassified','warning')],['Last successful snapshot',p=>esc(p.last_success||'Not recorded / exempt')],['Latest snapshot',p=>badge(p.latest_snapshot_state||'Not recorded',tone(p.latest_snapshot_state))],['Reason / schedule',p=>title(p.backup_cron||p.backup_exempt_reason||'Review coverage',p.latest_snapshot_failure_class)]],{placeholder:'Search claim, backup failure or exemption…'});
    section(callout('Restore verification is a separate result.','A Completed Restore can represent the configured NoSnapshot path. Confirm a real snapshot was selected and validate recovered application data before claiming a tested restore.'));
  }
  function renderPlan(){
    panel.innerHTML=head('07','Next repairs, ranked by consequence.','Use the latest verified faults to sequence work, and keep each change small enough to review. Hardware purchases follow evidence and fit checks.') + recheck('plan');
    const findings=D.reinspection?.plan?.findings || [];
    section(`<div class="repair-list">${findings.map(f=>`<article class="repair-card ${esc(f.status||'warning')}"><div class="card-meta">${badge(f.priority||'Review',f.status||'warning')}<span class="small">${esc(f.state||'Open')}</span></div><h3>${esc(f.title)}</h3><span class="label">Evidence</span><p>${esc(evidenceText(f.evidence))}</p><span class="label">Next action</span><p>${esc(evidenceText(f.action))}</p><span class="label">Pass the reinspection</span><p>${esc(evidenceText(f.verify))}</p></article>`).join('')}</div>`);
    section('<h3 class="subheading">Hardware decisions</h3><p class="body-copy">Open a drive in the first tab for its full reasoning and replacement constraints. Planned age, wear and cooling work is separate from a confirmed service outage.</p>');
    table(panel,disks,[['Drive',d=>`<button class="disk-link" data-disk="${esc(d.id)}">${esc(d.model)} ↗</button>${small(hostName(d.host))}`],['Priority',d=>badge(d.assessment.priority,priorityTone(d.assessment.priority))],['Decision',d=>title(d.assessment.verdict,d.assessment.reason)]],{placeholder:'Search hardware decision…'});
  }
  const stages=[['Disks',renderDisks],['Memory & CPU',renderResources],['Spread & replicas',renderSpread],['Disk thrashing',renderThrash],['Argo CD',renderArgo],['Pod health',renderHealth],['Repair plan',renderPlan]];
  const tabs=document.querySelector('#stage-tabs');let current=0;
  stages.forEach(([label],i)=>{const b=document.createElement('button');b.className='stage-tab';b.id=`tab-${i}`;b.setAttribute('role','tab');b.setAttribute('aria-controls','inspection-panel');b.innerHTML=`<span class="num">${i+1}</span>${esc(label)}`;b.addEventListener('click',()=>selectStage(i));b.addEventListener('keydown',e=>{let next=null;if(e.key==='ArrowRight')next=(i+1)%stages.length;if(e.key==='ArrowLeft')next=(i+stages.length-1)%stages.length;if(e.key==='Home')next=0;if(e.key==='End')next=stages.length-1;if(next!==null){e.preventDefault();selectStage(next);tabs.children[next].focus();tabs.children[next].scrollIntoView({block:'nearest',inline:'nearest'});}});tabs.append(b);});
  function selectStage(i){current=i;[...tabs.children].forEach((b,j)=>{b.setAttribute('aria-selected',String(i===j));b.tabIndex=i===j?0:-1;});panel.setAttribute('aria-labelledby',`tab-${i}`);stages[i][1]();history.replaceState(null,'',`#stage-${i+1}`);}
  document.querySelector('#capture-date').textContent=`Latest reinspection: ${date(D.reinspection?.checkedAt)} · Fresh physical checks: ${date(D.physicalCheckedAt || D.hardwareCheckedAt)}`;
  document.querySelector('#scope-counts').innerHTML=`<span><strong>${hosts.length}</strong>physical hosts</span><span><strong>${disks.length}</strong>drives</span><span><strong>${nodes.length}</strong>Talos nodes</span>`;
  document.querySelector('#revision').textContent=`Baseline ${D.sourceCommit||'not recorded'} · Dated inspection, not live polling`;
  panel.addEventListener('click',e=>{const b=e.target.closest('[data-disk]');if(b&&!document.querySelector('#detail-dialog').open)showDisk(b.dataset.disk);});
  const dialog=document.querySelector('#detail-dialog');document.querySelector('#close-detail').addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>{if(!dialog.open)history.replaceState(null,'',`#stage-${current+1}`);});dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  document.querySelector('#download').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(D,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='homelab-hardware-inspection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  window.addEventListener('hashchange',()=>{const match=location.hash.match(/^#drive-(.+)$/);if(match){if(dialog.open)dialog.close();showDisk(decodeURIComponent(match[1]));}});
  const driveMatch=location.hash.match(/^#drive-(.+)$/);
  const initial=Number(location.hash.match(/^#stage-([1-7])$/)?.[1]||1)-1;selectStage(initial);
  if(driveMatch)showDisk(decodeURIComponent(driveMatch[1]));
})();
