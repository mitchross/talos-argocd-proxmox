(function () {
  "use strict";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const capacity = bytes => bytes >= 1e12 ? `${(bytes / 1e12).toFixed(2).replace(/\.00$/, "")} TB` : `${Math.round(bytes / 1e9)} GB`;
  const gib = bytes => (bytes / 1024 ** 3).toFixed(1);

  function mount(root, data) {
    root.dataset.ready = "true";
    const state = {host: "sff", tab: "disks", proposed: false, outage: "sff", network: "private"};
    const hosts = data.hosts;
    const getHost = id => hosts.find(h => h.id === id);
    const button = (action, value, text, active) => `<button type="button" data-action="${action}" data-value="${escape(value)}" aria-pressed="${active}">${escape(text)}</button>`;
    root.innerHTML = `
      <div class="lab-top">
        <div class="lab-counts">
          <div><strong>${hosts.length}</strong><span>physical machines</span></div>
          <div><strong>${hosts.flatMap(h => h.vms).filter(v => v.ip).length}</strong><span>Kubernetes nodes</span></div>
          <div><strong>${hosts.reduce((n,h) => n+h.disks.length,0)}</strong><span>physical drives</span></div>
        </div>
        <div class="lab-toggle" aria-label="Machine role view" id="lab-role-toggle"></div>
      </div>
      <p class="lab-caption" id="lab-role-caption"></p>
      <div class="lab-machines" id="lab-machines" aria-label="Choose a physical machine"></div>
      <section class="lab-detail" aria-label="Selected machine" id="lab-detail"></section>
      <section class="lab-detail" id="lab-network" aria-label="Network paths and addresses"></section>
      <div class="lab-footer"><button type="button" class="lab-action" data-action="download">Download full inventory</button><span>Snapshot: ${escape(data.date)} · VM and physical-host IPs are separate.</span></div>`;
    const $ = selector => root.querySelector(selector);

    function renderNav() {
      $("#lab-role-toggle").innerHTML = button("mode","current","Audit snapshot",!state.proposed)+button("mode","proposed","Suggested jobs",state.proposed);
      $("#lab-role-caption").textContent = state.proposed ? "Suggested roles only. These placement changes have not been applied." : "September 5 snapshot, before the Talos upgrade. Choose a machine to look inside.";
      $("#lab-machines").innerHTML = hosts.map(h => `
        <button type="button" class="lab-machine" data-action="host" data-value="${escape(h.id)}" data-kind="${escape(h.kind)}" aria-pressed="${h.id===state.host}">
          <span class="lab-machine-name">${escape(h.name)}</span>
          <span class="lab-ip">${escape(h.ip)}</span>
          <span class="lab-role">${escape(state.proposed ? h.suggested : h.role)}</span>
          <span class="lab-meta">${escape(h.ram)} RAM · ${h.disks.length} ${h.disks.length===1?"drive":"drives"}</span>
        </button>`).join("");
    }

    function diskView(h) {
      const max = Math.max(...h.disks.map(d => d.bytes));
      const ram = h.memory ? `<h3>That RAM is being used</h3><div class="lab-memory" role="img" aria-label="340.5 GiB ZFS cache, 13.6 GiB services, 23.5 GiB free">${h.memory.map(m => `<span style="width:${m.gib/377.6*100}%"></span>`).join("")}</div><div class="lab-facts">${h.memory.map(m=>`<span>${escape(m.name)}: <strong>${m.gib} GiB</strong></span>`).join("")}</div><p>Keep the RAM. Cache size shows it is occupied; read reuse tells us how much it helps. No reduction was justified by this audit.</p>` : "";
      const pools = h.pools ? `<h3>How the NAS disks are grouped</h3><div class="lab-pools">${h.pools.map(p=>`<article class="lab-pool"><strong>${escape(p.name)}</strong><p>${escape(p.layout)}</p><div class="lab-bar" role="img" aria-label="${p.used}% allocated"><span style="width:${p.used}%"></span></div><p>${p.used}% allocated · ${escape(p.size)} pool</p><p>${escape(p.note)}</p></article>`).join("")}</div>` : "";
      return `${ram}${pools}<h3>Every physical drive</h3><p class="lab-caption">Bars compare raw capacity within this machine. Open a drive for its path and findings.</p>
        <div class="lab-disk-grid">${h.disks.map(d=>`<details class="lab-disk"><summary><span class="lab-size">${capacity(d.bytes)}</span> · ${escape(d.device)}<span class="lab-model">${escape(d.model)}</span><span class="lab-model">${escape(d.role)}</span></summary><div class="lab-bar" role="img" aria-label="${escape(capacity(d.bytes))} capacity"><span style="width:${d.bytes/max*100}%"></span></div><p><strong>${escape(d.role)}</strong></p><p>${gib(d.bytes)} GiB raw · ${escape(d.interface)}</p><div class="lab-path">${escape(d.path)}</div><p>${escape(d.note)}</p></details>`).join("")}</div>`;
    }

    function vmView(h) {
      if (!h.vms.length) return `<p>${h.id==="nas" ? "TrueNAS and RustFS run outside Kubernetes. This inventory did not enumerate NAS-managed guest VMs or containers." : "Omni and Technitium run on this Pi. It is not one of the Talos worker VMs."}</p><p class="lab-advice">${escape(h.summary)}</p>`;
      return `<p class="lab-caption">VM IDs and allocations come from Proxmox. Namespace counts are running pods at the audit snapshot.</p><div class="lab-vms">${h.vms.map(v=>`<article class="lab-vm"><strong>VM ${escape(v.id)} · ${v.ip ? escape(v.ip) : "No running guest IP recorded"}</strong><div class="lab-vm-name">${escape(v.name)}</div><div class="lab-facts"><span>${(v.ramMiB/1024).toFixed(1)} GiB RAM</span><span>${v.vcpus} vCPU</span><span>${escape(v.state)} at collection</span></div>${v.talos?`<p class="lab-caption">${escape(v.talos)} · Kubernetes ${escape(v.kubernetes)}</p>`:""}<ul>${v.disks.map(d=>`<li><strong>${escape(d.slot)} · ${escape(d.size)}</strong><div class="lab-path">${escape(d.backing)}</div></li>`).join("")}</ul>${v.namespaces.length ? `<details><summary>Apps and system namespaces (${v.namespaces.length})</summary><div class="lab-chip-list">${v.namespaces.map(n=>`<span class="lab-chip">${escape(n.name)} · ${n.pods}</span>`).join("")}</div></details>`:""}</article>`).join("")}</div>`;
    }

    function affected(h) {
      if (h.id==="nas") return data.claims.filter(c=>/nfs|smb|truenas/.test(c.csi_driver)).map(c=>({claim:c,text:"NAS path unavailable; operations may stall."}));
      return data.claims.filter(c=>c.replica_zones.split(",").includes(h.zone)).map(c=>({claim:c,text:c.replica_zones.split(",").filter(z=>z&&z!==h.zone).length ? "Another physical host held a copy. Recovery still needs healthy replicas, the API and eligible compute." : "Only recorded host copy is here. Rescheduling cannot create the missing data."}));
    }

    function outageView() {
      const h=getHost(state.outage), rows=affected(h);
      return `<div class="lab-outage"><label for="lab-outage-host"><strong>What if this machine stops?</strong></label><select id="lab-outage-host">${hosts.map(x=>`<option value="${escape(x.id)}" ${x.id===h.id?"selected":""}>${escape(x.name)} · ${escape(x.ip)}</option>`).join("")}</select><p class="lab-caption">A dependency walkthrough. This does not touch the lab or predict a recovery time.</p><div class="lab-outcome"><strong>${escape(h.name)} disappears</strong><p>${escape(h.loss)}</p></div><div class="lab-outcome"><strong>What would improve this?</strong><p>${escape(h.advice)}</p></div>${h.id==="nas"?'<p>Kopiur restore waits for RustFS. NAS downtime is accepted; binding an empty replacement during an outage is not.</p>':""}${rows.length?`<details><summary>${rows.length} recorded claims with this storage dependency</summary>${rows.map(({claim:c,text})=>`<div class="lab-claim"><strong>${escape(c.namespace)} / ${escape(c.claim)}</strong><br>${escape(c.requested_storage)} · ${escape(c.storage_class||c.csi_driver)}<br>${escape(text)}</div>`).join("")}</details>`:'<p>No Longhorn/NAS claim placements in this snapshot are attributed to this host. That does not remove its device or management dependencies.</p>'}</div>`;
    }

    function renderNetwork() {
      const net=data.network, path=net.paths.find(p=>p.id===state.network);
      $("#lab-network").innerHTML=`<h2>How things connect</h2><div class="lab-toggle" aria-label="Choose a network path">${net.paths.map(p=>button("network",p.id,p.name,p.id===state.network)).join("")}</div><div class="lab-network-flow">${path.steps.map((s,i)=>`<div><span class="lab-caption">${i+1}</span><strong>${escape(s.title)}</strong><p>${escape(s.text)}</p></div>`).join("")}</div><p>${escape(path.note)}</p><details><summary>Other recorded network addresses</summary>${net.addresses.map(a=>`<div class="lab-claim"><strong>${escape(a.name)} · ${escape(a.ip)}</strong><br>${escape(a.role)}</div>`).join("")}<p class="lab-caption">${escape(net.source)}</p><p class="lab-caption">10G switch model and management IP were not captured.</p></details>`;
    }

    function renderDetail() {
      const h=getHost(state.host);
      $("#lab-detail").innerHTML = `<button type="button" class="lab-action lab-back" data-action="back">↑ Pick another machine</button><h2>${escape(h.name)}</h2><p>${escape(h.summary)}</p><div class="lab-facts"><span><strong>Host:</strong> ${escape(h.ip)}</span><span>${escape(h.model)}</span><span>${escape(h.cpu)}</span><span>${escape(h.ram)} installed</span><span>${escape(h.link)}</span><span><strong>Zone:</strong> ${escape(h.zone||"outside Kubernetes")}</span></div>${h.power!==null?`<p class="lab-caption">Power sample: ~${h.power} W${h.extraPower?` · ${escape(h.extraPower)}`:""}. One reading, not an average.</p>`:h.id==="sff"||h.id==="dell"?'<p class="lab-caption">SFF + Dell shared plug: ~63 W combined at collection. Per-host power was not separated.</p>':""}${state.proposed?`<p class="lab-advice"><strong>My suggested job: ${escape(h.suggested)}</strong><br>${escape(h.advice)}</p>`:""}<div class="lab-tabs lab-toggle" aria-label="Machine detail">${button("tab","disks","Disks & memory",state.tab==="disks")}${button("tab","vms","VMs & apps",state.tab==="vms")}${button("tab","outage","What if it stops?",state.tab==="outage")}</div><div id="lab-content">${state.tab==="disks"?diskView(h):state.tab==="vms"?vmView(h):outageView()}</div>`;
    }

    root.addEventListener("click", event => {
      const target=event.target.closest("button[data-action]");
      if (!target || !root.contains(target)) return;
      const {action,value}=target.dataset;
      if (action==="network") {state.network=value;renderNetwork();root.querySelector(`button[data-action="network"][data-value="${value}"]`).focus({preventScroll:true});return;}
      if (action==="back") {$("#lab-machines").scrollIntoView({block:"start"});root.querySelector(`button[data-action="host"][data-value="${state.host}"]`).focus({preventScroll:true});return;}
      if (action==="download") {
        const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));
        const link=document.createElement("a");link.href=url;link.download=`homelab-inventory-${data.date}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;
      }
      if (action==="host") {state.host=value;state.outage=value;}
      if (action==="mode") state.proposed=value==="proposed";
      if (action==="tab") state.tab=value;
      renderNav();renderDetail();
      const focused=root.querySelector(`button[data-action="${action}"][data-value="${value}"]`);if(focused)focused.focus({preventScroll:true});
      if(action==="host")$("#lab-detail").scrollIntoView({block:"start"});
    });
    root.addEventListener("change", event => {
      if(event.target.id!=="lab-outage-host")return;
      state.outage=event.target.value;state.host=state.outage;renderNav();renderDetail();$("#lab-outage-host").focus({preventScroll:true});
    });
    renderNav();renderDetail();renderNetwork();
  }

  function init() {
    const root=document.getElementById("lab-explorer");
    if(root&&!root.dataset.ready&&window.HOMELAB_INVENTORY)mount(root,window.HOMELAB_INVENTORY);
  }
  if(typeof document$!=="undefined")document$.subscribe(init);
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
