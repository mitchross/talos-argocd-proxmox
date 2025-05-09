// Pulumi program to deploy a 3-node Talos Kubernetes cluster
import * as pulumi from "@pulumi/pulumi";
import * as command from "@pulumi/command";

// Configuration
const config = new pulumi.Config();
const nodeIps = config.requireObject<string[]>("nodeIps");
const vip = config.get("vip");
const talosctlPath = config.get("talosctlPath") || "talosctl";
const talosOutputDir = config.get("talosOutputDir") || "./talos";
const nodeConfig = config.requireObject<Array<{
  ip: string;
  hostname: string;
  filename: string;
  deviceSelector: { busPath: string };
}>>('nodeConfig');
const machine = config.requireObject<{
  install: {
    image: string;
  };
}>('machine');
const kubernetes = config.get("kubernetes");
const machineInstallImage = config.requireObject<any>("machine").install.image;

// Make sure the output directory exists
const ensureOutputDir = new command.local.Command("ensure-output-dir", {
  create: `mkdir -p ${talosOutputDir}`,
});

// Generate secrets once and use for all nodes
const talosSecrets = new command.local.Command("generate-talos-secrets", {
  create: pulumi.interpolate`
    ${talosctlPath} gen secrets -o ${talosOutputDir}/secrets.yaml --force
    `,
  triggers: [ensureOutputDir.id]
});

// Generate the talosconfig file
const talosConfigFile = new command.local.Command("generate-talosconfig", {
  create: pulumi.interpolate`
    # Check if secrets file exists
    while [ ! -f "${talosOutputDir}/secrets.yaml" ]; do
        echo "Waiting for secrets file..."
        sleep 1
    done
    
    # Generate Talos configuration with the shared secrets
    ${talosctlPath} gen config --with-secrets ${talosOutputDir}/secrets.yaml \
    --output ${talosOutputDir}/talosconfig \
    --output-types talosconfig \
    --force \
    vanillax-proxmox-talos https://${vip}:6443
    `,
  triggers: [talosSecrets.id]
});

const generateNodeConfigs = new command.local.Command("generate-node-configs", {
  create: pulumi.interpolate`
    # Wait for secrets file to be fully created
    if [ ! -f "${talosOutputDir}/secrets.yaml" ]; then
        echo "Error: Secrets file not found. This command depends on secrets generation."
        exit 1
    fi
    
    # Extract versions from config
    k8s_version="${kubernetes}"
    talos_image="${machineInstallImage}"
    echo "Using Kubernetes version: $k8s_version"
    echo "Using Talos image: $talos_image"
    
    # Create a JSON file with the nodeConfig data to access in the shell
    cat > ${talosOutputDir}/node-config.json << EOF
${JSON.stringify(nodeConfig)}
EOF
    
    # Generate configs for each node with specific patches
    count=$(jq '. | length' ${talosOutputDir}/node-config.json)
    for i in $(seq 0 $(($count - 1))); do
        ip=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].ip")
        hostname=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].hostname")
        filename=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].filename")
        busPath=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].deviceSelector.busPath")
        
        # Create node-specific patch file
        cat > ${talosOutputDir}/patch-$i.json << EOF
[
  {
    "op": "add",
    "path": "/machine/network/hostname",
    "value": "$hostname"
  },
  {
    "op": "add",
    "path": "/machine/network/interfaces",
    "value": [
      {
        "deviceSelector": {
          "busPath": "$busPath"
        },
        "dhcp": false,
        "addresses": ["$ip/24"],
        "mtu": 1500,
        "routes": [
          {
            "network": "0.0.0.0/0",
            "gateway": "192.168.10.1"
          }
        ],
        "vip": {
          "ip": "${vip}"
        }
      }
    ]
  },
  {
    "op": "add",
    "path": "/machine/certSANs",
    "value": [
      "${vip}",
      "$ip",
      "127.0.0.1"
    ]
  },
  {
    "op": "add", 
    "path": "/machine/install/image",
    "value": "$talos_image"
  },
  {
    "op": "add",
    "path": "/cluster/apiServer/certSANs",
    "value": [
      "${vip}",
      "$ip",
      "127.0.0.1"
    ]
  }
]
EOF
        
        # Generate config for this specific node
        ${talosctlPath} gen config \
          --with-secrets ${talosOutputDir}/secrets.yaml \
          --config-patch-control-plane '[{"op": "add", "path": "/cluster/allowSchedulingOnControlPlanes", "value": true}]' \
          --config-patch-control-plane @${talosOutputDir}/patch-$i.json \
          --kubernetes-version $k8s_version \
          --output ${talosOutputDir}/$filename \
          --output-types controlplane \
          --force \
          vanillax-proxmox-talos https://${vip}:6443
        
        echo "Generated $filename for $hostname ($ip)"
    done
    `,
  triggers: [talosConfigFile.id]
});

// Configure talosctl endpoints using the generated files
const configureEndpoints = new command.local.Command("configure-endpoints", {
  create: pulumi.interpolate`
    # Ensure config files exist
    # Ensure node-config.json exists (created by generate-node-configs)
    if [ ! -f "${talosOutputDir}/node-config.json" ]; then
        echo "Error: ${talosOutputDir}/node-config.json not found. This command depends on generate-node-configs."
        exit 1
    fi
    for file in $(jq -r '.[].filename' "${talosOutputDir}/node-config.json"); do
        if [ ! -f "${talosOutputDir}/$file" ]; then
            echo "Error: Config file ${talosOutputDir}/$file not found. This command depends on config generation."
            exit 1
        fi
    done
    
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    ${talosctlPath} config endpoints ${nodeIps.join(" ")}
    ${talosctlPath} config nodes ${nodeIps.join(" ")}
    `,
  triggers: [generateNodeConfigs.id]
});

// Apply configurations to all nodes
const applyConfigs = nodeConfig.map((node, i) =>
  new command.local.Command(`apply-controlplane-config-${i}`, {
    create: pulumi.interpolate`
        export TALOSCONFIG=${talosOutputDir}/talosconfig
        ${talosctlPath} apply-config --insecure --nodes ${node.ip} --file ${talosOutputDir}/${node.filename}
        `,
    triggers: [configureEndpoints.id]
  })
);

// First, add a command to bootstrap the cluster
const bootstrapCluster = new command.local.Command("bootstrap-cluster", {
  create: pulumi.interpolate`
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    
    echo "Bootstrapping cluster on first node (${nodeIps[0]})..."
    
    # Bootstrap the cluster - this starts etcd and the control plane
    ${talosctlPath} bootstrap --nodes ${nodeIps[0]}
    
    echo "Waiting for API server to be available..."
    # Wait for API server to be ready
    for i in {1..30}; do
        if ${talosctlPath} health --server=false 2>/dev/null; then
            echo "API server is ready!"
            break
        fi
        echo "Waiting for API server... ($i/30)"
        sleep 10
    done
    `,
  // Run after all configs are applied
  triggers: applyConfigs.map(cmd => cmd.id)
});

// Then wait for all nodes to join
const waitForNodes = new command.local.Command("wait-for-nodes", {
  create: pulumi.interpolate`
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    
    echo "Waiting for all nodes to be ready..."
    
    # Wait for all nodes to be ready
    ${talosctlPath} health --server=false --wait-timeout=10m
    
    # Check that all control plane nodes are members
    echo "Checking cluster membership..."
    for ip in ${nodeIps.join(" ")}; do
        echo "Checking node $ip..."
        ${talosctlPath} get members --nodes $ip
    done
    `,
  triggers: [bootstrapCluster.id]
});

// Get the kubeconfig with improved error handling
const kubeconfig = new command.local.Command("get-kubeconfig", {
  create: pulumi.interpolate`
    # Save talosconfig for reference
    TALOSCONFIG=${talosOutputDir}/talosconfig
    
    # Try to get kubeconfig directly using the standard method
    echo "Retrieving kubeconfig..."
    ${talosctlPath} --talosconfig=$TALOSCONFIG --nodes ${nodeIps[0]} kubeconfig ${talosOutputDir}/kubeconfig
    
    # Check if kubeconfig was successfully created
    if [ -f "${talosOutputDir}/kubeconfig" ] && [ -s "${talosOutputDir}/kubeconfig" ]; then
        echo "Successfully generated kubeconfig at ${talosOutputDir}/kubeconfig"
    else
        echo "Failed to create a valid kubeconfig file"
        exit 1
    fi
    `,
  triggers: [waitForNodes.id]
});

const ciliumInstall = new command.local.Command("install-cilium", {
  create: pulumi.interpolate`
  export KUBECONFIG=${talosOutputDir}/kubeconfig
  
  # Add permissive PSA labels to kube-system
  kubectl label --overwrite namespace kube-system \
    pod-security.kubernetes.io/enforce=privileged \
    pod-security.kubernetes.io/audit=privileged \
    pod-security.kubernetes.io/warn=privileged
  
  # Install Cilium using Helm CLI with Talos-specific settings
  helm repo add cilium https://helm.cilium.io/
  helm repo update
  
  helm upgrade --install cilium cilium/cilium \
    --version 1.17.3 \
    --namespace kube-system \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=false \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set apparmor.enabled=false \
    --set enableCriticalPriorityClass=false \
    --set priorityClassName=""
  
  # Verify installation
  kubectl -n kube-system get pods -l k8s-app=cilium
  `,
  triggers: [kubeconfig.id],
});

// Export the necessary information
export const talosconfigPath = `${talosOutputDir}/talosconfig`;
export const kubeconfigPath = `${talosOutputDir}/kubeconfig`;
export const clusterEndpoint = `https://${vip}:6443`;
// export const ciliumStatus = ciliumChart.ready;