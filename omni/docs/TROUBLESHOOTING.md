# Troubleshooting Guide

Common issues and solutions for the Omni + Talos + Proxmox stack.

## Omni Issues

### Cannot Access Omni UI

**Symptom**: Browser cannot reach `https://omni.yourdomain.com`

**Diagnosis**:
```bash
# Check if Omni container is running
docker compose ps

# Check Omni logs
docker compose logs omni | tail -50

# Check if port 443 is listening
sudo netstat -tulpn | grep :443

# Test DNS resolution
nslookup omni.yourdomain.com

# Test connectivity
curl -k https://omni.yourdomain.com
```

**Solutions**:
1. **Container not running**: `docker compose up -d`
2. **Port conflict**: Another service using port 443
   - Check: `sudo lsof -i :443`
   - Stop conflicting service or change Omni port
3. **Firewall blocking**:
   ```bash
   sudo ufw allow 443/tcp
   sudo ufw allow 8090/tcp
   sudo ufw allow 8099/tcp
   sudo ufw allow 51821/udp
   ```
4. **DNS not resolving**: Update DNS A record
5. **Certificate issues**: Verify cert paths in `omni.env`

### Omni Won't Start

**Symptom**: Container exits immediately or restarts continuously

**Diagnosis**:
```bash
# Check logs for errors
docker compose logs omni

# Common errors to look for:
# - "permission denied" → volume permission issues
# - "address already in use" → port conflicts
# - "failed to decrypt" → GPG key issues
# - "certificate" errors → SSL cert issues
```

**Solutions**:

**Permission denied on etcd**:
```bash
sudo chown -R 1000:1000 /etc/etcd
sudo chmod -R 700 /etc/etcd
```

**Port already in use**:
```bash
# Find process using port
sudo lsof -i :443
# Kill it or change Omni port in omni.env
```

**GPG key issues**:
```bash
# Verify key file exists
ls -la /path/to/omni.asc

# Verify key is valid
gpg --import /path/to/omni.asc
gpg --list-keys

# Re-export if needed
gpg --export-secret-key --armor your-email@example.com > omni.asc
```

**Certificate issues**:
```bash
# Verify cert files exist
ls -la /etc/letsencrypt/live/omni.yourdomain.com/

# Check cert is valid
openssl x509 -in /etc/letsencrypt/live/omni.yourdomain.com/fullchain.pem -text -noout

# Verify cert hasn't expired
openssl x509 -in /etc/letsencrypt/live/omni.yourdomain.com/fullchain.pem -noout -dates
```

### Authentication Fails

**Symptom**: Cannot log in via Auth0/SAML/OIDC

**Auth0 Issues**:
1. Verify callback URLs match exactly:
   - Allowed Callback URLs: `https://omni.yourdomain.com:443/oidc/callback`
   - Allowed Logout URLs: `https://omni.yourdomain.com:443/`
   - Allowed Web Origins: `https://omni.yourdomain.com:443`

2. Check Auth0 config in `omni.env`:
   ```bash
   # Verify domain format
   AUTH0_DOMAIN=your-tenant.us.auth0.com
   # NOT: https://your-tenant.us.auth0.com
   ```

3. Verify initial user email matches Auth0 account:
   ```bash
   # In omni.env
   INITIAL_USER_EMAILS=user@example.com
   # Must match email in Auth0
   ```

**SAML/OIDC Issues**:
- Check provider metadata/configuration
- Verify certificates are valid
- Check claim mappings (email, name, etc.)

### Nodes Not Connecting

**Symptom**: Talos nodes not appearing in Omni or stuck in "Connecting"

**Diagnosis**:
```bash
# On Talos node, check connectivity
talosctl -n <node-ip> get members

# Check SideroLink status
talosctl -n <node-ip> get links
```

**Solutions**:

**WireGuard issues**:
1. Verify WireGuard IP in `omni.env`:
   ```bash
   # Should be actual IP, not domain
   SIDEROLINK_WIREGUARD_ADVERTISED_ADDR=10.0.0.100:51821
   ```

2. Check UDP port 51821 is open:
   ```bash
   sudo ufw allow 51821/udp
   ```

3. Verify Talos can reach Omni:
   ```bash
   # From Proxmox host, test connectivity
   nc -vz omni-host-ip 51821
   ```

**Network issues**:
- Ensure VMs have network connectivity
- Check Proxmox network bridge configuration
- Verify DHCP is working (or configure static IPs)

## Proxmox Provider Issues

### Provider Won't Start

**Symptom**: Container exits or won't start

**Diagnosis**:
```bash
# Check logs
docker compose logs omni-infra-provider-proxmox

# Look for:
# - Connection refused → Omni or Proxmox unreachable
# - Authentication failed → Wrong credentials
# - Invalid API key → Wrong infrastructure provider key type
```

**Solutions**:

**Connection refused to Omni**:
```bash
# Verify Omni is accessible
curl https://omni.yourdomain.com

# Check OMNI_API_ENDPOINT in .env
# Should be: https://omni.yourdomain.com/
# Include trailing slash!
```

**Connection refused to Proxmox**:
```bash
# Test Proxmox API
curl -k https://proxmox-ip:8006/api2/json/version

# Check network connectivity
ping proxmox-ip
```

**Authentication failed**:
```bash
# Verify credentials in config.yaml
# Username format: root@pam (not just root)
# Password: correct password

# Test login manually
pvesh get /version --username root@pam
```

**Wrong key type**:
- Ensure you're using an **Infrastructure Provider Key**
- NOT a service account key
- Generate in Omni UI: Settings → Infrastructure Providers

### VMs Not Being Created

**Symptom**: Cluster created but VMs don't appear in Proxmox

**Diagnosis**:
```bash
# Check provider logs for errors
docker compose logs -f omni-infra-provider-proxmox

# Common errors:
# - Storage selection failed → CEL expression issue
# - Insufficient permissions → User permissions
# - API errors → Proxmox API issues
```

**Solutions**:

**Storage selection failed**:
```bash
# Test storage query in Proxmox
pvesh get /storage

# Verify storage is enabled and active
# Update CEL expression in machine class if needed

# Example: Select any active storage
storage.filter(s, s.enabled && s.active)[0].storage
```

**Permission issues**:
```bash
# If using non-root user, verify permissions
pveum user permissions omni@pve

# Grant required permissions:
pveum aclmod / -user omni@pve -role PVEVMAdmin
```

**Storage full**:
```bash
# Check available space
pvesh get /storage --enabled 1

# Free up space or select different storage
```

### VMs Created But Won't Boot

**Symptom**: VMs exist but don't boot or get stuck

**Diagnosis**:
```bash
# Check Proxmox console for VM
# Look at boot messages

# Common issues:
# - No network → VM can't reach Omni
# - Wrong boot order → Not booting from Talos image
# - Insufficient resources → Not enough RAM/CPU
```

**Solutions**:

**Network issues**:
1. Verify VM has network interface
2. Check Proxmox bridge configuration
3. Verify DHCP is working

**Boot order**:
1. In Proxmox, check VM hardware
2. Verify boot order has CD/ISO first
3. Check Talos ISO is attached

**Resource issues**:
1. Check machine class specs are reasonable
2. Verify Proxmox host has available resources
3. Reduce VM specs if needed

## Talos Cluster Issues

### Cluster Won't Bootstrap

**Symptom**: Cluster stuck in "Bootstrapping" state

**Diagnosis**:
```bash
# Check control plane logs in Omni UI
# Look for etcd issues

# Check node status
talosctl -n <control-plane-ip> get members
```

**Solutions**:

**Etcd issues**:
- Ensure odd number of control plane nodes (1, 3, or 5)
- Verify control plane nodes can communicate
- Check for time sync issues (NTP)

**Certificate issues**:
- Wait for Omni to generate certificates
- Check Omni logs for errors
- Verify nodes are registered in Omni

**Network issues**:
- Verify control plane nodes can reach each other
- Check Proxmox network configuration
- Verify no firewall blocking

### Nodes Stuck "Installing"

**Symptom**: Nodes show "Installing" status indefinitely in Omni

**Diagnosis**:
```bash
# Check Proxmox console for the VM
# Look for errors in boot output

# Common causes:
# - Extension download failing
# - Disk issues
# - Network connectivity
```

**Solutions**:

**Extension download failing** (GPU extensions):
- Nodes can't download extensions → check internet connectivity
- Try custom ISO with extensions pre-baked (see [talos-configs/README.md](../talos-configs/README.md))

**Disk issues**:
- Verify disk is large enough (minimum 50GB)
- Check Proxmox storage isn't full
- Verify disk I/O isn't bottlenecked

**Network issues**:
- Verify VM has working network
- Check DHCP is assigning IPs
- Test internet connectivity from VM

### Nodes Keep Rebooting

**Symptom**: Nodes repeatedly reboot and never stabilize

**Diagnosis**:
```bash
# Check node logs in Omni UI
# Watch Proxmox console during boot

# Common causes:
# - Configuration issues
# - Hardware incompatibility
# - Kernel panics
```

**Solutions**:

**Configuration issues**:
- Check machine config patches for errors
- Verify no conflicting patches
- Try minimal config first

**Hardware issues** (rare in VMs):
- Increase VM resources
- Check Proxmox host stability
- Try different Proxmox node

**Kernel issues**:
- Update to latest Talos version
- Check Talos GitHub issues for known problems
- Report issue to Sidero Labs

## GPU-Specific Issues

### Extensions Not Installing

**Symptom**: Cluster stuck on "Installing" with GPU extensions

**Context**: This is a known issue. See discussion in [talos-configs/README.md](../talos-configs/README.md).

**Solutions**:

**Solution 1**: Use custom ISO with extensions pre-baked
```bash
docker run --rm -i \
  ghcr.io/siderolabs/imager:v1.11.0 \
  iso \
  --system-extension-image ghcr.io/siderolabs/nonfree-kmod-nvidia:550.127.05-v1.11.0 \
  --system-extension-image ghcr.io/siderolabs/nvidia-container-toolkit:550.127.05-v1.11.0-v1.16.2
```

**Solution 2**: Check Proxmox console/tty settings
- Some users report tty configuration issues prevent installation
- Try different console settings in Proxmox VM config

**Solution 3**: Verify network connectivity
- Extensions must be downloaded during installation
- Ensure VMs have internet access
- Check for proxy/firewall blocking downloads

### GPU Modules Not Loading

**Symptom**: Extensions installed but `nvidia-smi` fails or modules not in `/proc/modules`

**Diagnosis**:
```bash
# Check if extensions are present
talosctl -n <node-ip> get extensions

# Check if modules are loaded
talosctl -n <node-ip> read /proc/modules | grep nvidia
```

**Solutions**:

**Modules not loaded**:
1. Extensions being present doesn't auto-load modules
2. You must apply the machine config patch
3. See [talos-configs/gpu-worker-patch.yaml](../talos-configs/gpu-worker-patch.yaml)

**Patch not applied**:
1. Verify patch exists in Omni
2. Check patch is applied to correct machine class or nodes
3. Reboot node after applying patch: `talosctl -n <node-ip> reboot`

**Version mismatch**:
1. Ensure both extensions have matching driver versions
2. Example: Both should be 550.127.05
3. Check extension compatibility with Talos version

### GPU Not Passed Through

**Symptom**: Modules load but GPU not visible in `nvidia-smi`

**This is a Proxmox configuration issue**, not Talos.

**Diagnosis**:
```bash
# On Proxmox host, check GPU is available
lspci | grep -i nvidia

# Check GPU is assigned to VM
qm config <vmid> | grep hostpci
```

**Solutions**:

1. **Enable IOMMU** (if not already):
   ```bash
   # Edit /etc/default/grub
   # Intel: GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"
   # AMD: GRUB_CMDLINE_LINUX_DEFAULT="quiet amd_iommu=on iommu=pt"

   update-grub
   reboot
   ```

2. **Load VFIO modules**:
   ```bash
   # Add to /etc/modules
   vfio
   vfio_iommu_type1
   vfio_pci
   vfio_virqfd

   update-initramfs -u -k all
   reboot
   ```

3. **Bind GPU to VFIO**:
   ```bash
   # Find GPU PCI ID
   lspci -nn | grep -i nvidia
   # Example: 10de:1e87

   # Add to /etc/modprobe.d/vfio.conf
   options vfio-pci ids=10de:1e87,10de:10f8

   # Blacklist nouveau
   # Add to /etc/modprobe.d/blacklist.conf
   blacklist nouveau

   update-initramfs -u -k all
   reboot
   ```

4. **Assign to VM**:
   ```bash
   qm set <vmid> -hostpci0 01:00,pcie=1,rombar=0
   ```

### GPU Works in Talos But Not in Pods

**Symptom**: `talosctl read /proc/driver/nvidia/version` works but pods can't access GPU

**Solutions**:

**Missing RuntimeClass**:
```yaml
# Create RuntimeClass
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: nvidia
handler: nvidia
```

**Missing device plugin**:
```bash
# Install NVIDIA device plugin
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm install nvidia-device-plugin nvdp/nvidia-device-plugin \
  --namespace kube-system \
  --set runtimeClassName=nvidia
```

**Pod not requesting GPU**:
```yaml
# Pod must specify:
spec:
  runtimeClassName: nvidia  # Add this
  containers:
  - name: gpu-app
    resources:
      limits:
        nvidia.com/gpu: 1  # Add this
```

## Performance Issues

### Slow VM Creation

**Symptom**: VMs take a long time to create in Proxmox

**Causes**:
- Slow storage (especially over network)
- Large image downloads
- Resource contention

**Solutions**:
- Use faster storage (SSD/NVMe) for VM disks
- Cache Talos images locally in Proxmox
- Reduce concurrent VM creations

### Slow Cluster Operations

**Symptom**: Omni UI is slow, cluster operations take long time

**Causes**:
- Omni server under-resourced
- Network latency
- Large number of clusters/machines

**Solutions**:
- Increase Omni server resources
- Use SSD for etcd storage
- Optimize network between Omni and nodes

## Getting Help

### Before Asking for Help

Gather this information:
1. **Version information**:
   ```bash
   # Omni version
   docker inspect omni | grep OMNI_IMG_TAG

   # Talos version
   talosctl version --nodes <node-ip>

   # Provider version
   docker inspect omni-infra-provider-proxmox | grep image
   ```

2. **Logs**:
   ```bash
   # Omni logs
   docker compose logs omni > omni-logs.txt

   # Provider logs
   docker compose logs omni-infra-provider-proxmox > provider-logs.txt

   # Talos logs (from Omni UI or talosctl)
   ```

3. **Configuration** (sanitized):
   - omni.env (remove secrets)
   - config.yaml (remove credentials)
   - Machine class specs

### Where to Get Help

1. **Sidero Labs Slack**: [slack.dev.talos-systems.io](https://slack.dev.talos-systems.io/)
   - #omni channel
   - #talos channel

2. **GitHub Issues**:
   - [Omni Issues](https://github.com/siderolabs/omni/issues)
   - [Talos Issues](https://github.com/siderolabs/talos/issues)
   - [Provider Issues](https://github.com/siderolabs/omni-infra-provider-proxmox/issues)

3. **Documentation**:
   - [Omni Docs](https://docs.siderolabs.com/omni/)
   - [Talos Docs](https://docs.siderolabs.com/talos/)

### Reporting Bugs

When reporting bugs, include:
- Clear description of issue
- Steps to reproduce
- Expected vs actual behavior
- Version information
- Relevant logs
- Configuration (sanitized)

## Advanced Debugging

### Enable Debug Logging

**Omni**:
Add to command in docker-compose.yml:
```yaml
command: >
  --log-level=debug
  # ... other flags
```

**Talos**:
```bash
talosctl -n <node-ip> logs --follow kubelet
talosctl -n <node-ip> logs --follow machined
```

### Network Debugging

```bash
# Test Omni API connectivity
curl -v https://omni.yourdomain.com/api/omni.status

# Test Proxmox API
curl -k https://proxmox-ip:8006/api2/json/version

# Test DNS resolution
dig omni.yourdomain.com

# Check routing
traceroute omni.yourdomain.com

# Check firewalls
sudo iptables -L -n -v
```

### Container Debugging

```bash
# Exec into Omni container
docker exec -it omni sh

# Check running processes
docker exec omni ps aux

# Check container networking
docker exec omni ip addr
docker exec omni ip route

# Check container logs in real-time
docker logs -f omni
```
