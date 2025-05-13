// Pulumi program to deploy a Talos Kubernetes cluster
import * as pulumi from "@pulumi/pulumi";
import * as command from "@pulumi/command";

// Configuration
const config = new pulumi.Config();
const nodeIps = config.requireObject<string[]>("nodeIps"); // Control plane IPs for bootstrap/initial config
const vip = config.require("vip"); // VIP is required now due to logic separation
const talosctlPath = config.get("talosctlPath") || "talosctl";
const talosOutputDir = config.get("talosOutputDir") || "./talos";
const nodeConfig = config.requireObject<Array<{
  ip: string;
  hostname: string;
  filename: string;
  deviceSelector: { busPath: string };
  role: "controlplane" | "worker"; // Use specific roles for type safety
}>>('nodeConfig');
const machine = config.requireObject<{
  install: {
    image: string;
  };
}>('machine');
const kubernetes = config.require("kubernetes"); // Kubernetes version is required
const machineInstallImage = machine.install.image; // Simplified access

// Make sure the output directory exists
const ensureOutputDir = new command.local.Command("ensure-output-dir", {
  create: `mkdir -p ${talosOutputDir}`,
});

// Generate secrets once and use for all nodes
const talosSecrets = new command.local.Command("generate-talos-secrets", {
  create: pulumi.interpolate`
    echo "Attempting to generate secrets into ${talosOutputDir}/secrets.yaml"
    ${talosctlPath} gen secrets -o ${talosOutputDir}/secrets.yaml --force
    if [ $? -ne 0 ]; then
      echo "Error from generate-talos-secrets: talosctl gen secrets command failed with exit code $?."
      exit 1
    fi
    # Check for existence
    if [ ! -f "${talosOutputDir}/secrets.yaml" ]; then
      echo "Error from generate-talos-secrets: secrets.yaml NOT FOUND after talosctl gen secrets command."
      echo "Contents of ${talosOutputDir}:"
      ls -la "${talosOutputDir}"
      exit 1
    fi
    # Check for non-emptiness
    if [ ! -s "${talosOutputDir}/secrets.yaml" ]; then
      echo "Error from generate-talos-secrets: secrets.yaml IS EMPTY after talosctl gen secrets command."
      echo "Contents of ${talosOutputDir}:"
      ls -la "${talosOutputDir}"
      echo "Content of ${talosOutputDir}/secrets.yaml (if any):"
      cat "${talosOutputDir}/secrets.yaml"
      exit 1
    fi
    echo "secrets.yaml successfully created and is non-empty by generate-talos-secrets."
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

// Generate Node Configurations with Role-Specific Patches and Cluster Settings
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
    nodeConfigJson=$(cat <<EOF
${JSON.stringify(nodeConfig)}
EOF
)
    echo "$nodeConfigJson" > ${talosOutputDir}/node-config.json

    # Check if node-config.json was created
    if [ ! -f "${talosOutputDir}/node-config.json" ]; then
        echo "Error: Failed to create node-config.json."
        exit 1
    fi

    # Generate configs for each node with specific patches
    count=$(jq '. | length' ${talosOutputDir}/node-config.json)
    for i in $(seq 0 $(($count - 1))); do
        ip=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].ip")
        hostname=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].hostname")
        filename=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].filename")
        busPath=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].deviceSelector.busPath")
        role=$(cat ${talosOutputDir}/node-config.json | jq -r ".[$i].role")

        # Start of the node-specific patch array
        echo "[" > ${talosOutputDir}/patch-$i.json

        # Common patches for all roles
        cat >> ${talosOutputDir}/patch-$i.json << EOF
  {
    "op": "add",
    "path": "/machine/network/hostname",
    "value": "$hostname"
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
  }
EOF

        if [ "$role" = "controlplane" ]; then
          # Patches specific to control-plane for the node-specific file
          cat >> ${talosOutputDir}/patch-$i.json << EOF
,
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
    "path": "/cluster/apiServer/certSANs",
    "value": [
      "${vip}",
      "$ip",
      "127.0.0.1"
    ]
  }
EOF
        elif [ "$role" = "worker" ]; then
          # Patches specific to worker for the node-specific file
          cat >> ${talosOutputDir}/patch-$i.json << EOF
,
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
        ]
      }
    ]
  }
EOF
        else
            echo "Error: Unknown role '$role' for node $hostname"
            exit 1
        fi

        # End of the node-specific patch array
        echo "]" >> ${talosOutputDir}/patch-$i.json

        echo "Generating config for $filename (role: $role) with patch file ${talosOutputDir}/patch-$i.json..."

        if [ "$role" = "controlplane" ]; then
          ${talosctlPath} gen config \
            --with-secrets ${talosOutputDir}/secrets.yaml \
            --config-patch-control-plane '[
              {"op": "add", "path": "/cluster/allowSchedulingOnControlPlanes", "value": true},
              {"op": "add", "path": "/cluster/proxy", "value": {"disabled": true}},
              {"op": "add", "path": "/cluster/network/cni", "value": {"name": "none"}}
            ]' \
            --config-patch-control-plane @${talosOutputDir}/patch-$i.json \
            --kubernetes-version $k8s_version \
            --output ${talosOutputDir}/$filename \
            --output-types controlplane \
            --force \
            vanillax-proxmox-talos https://${vip}:6443
        elif [ "$role" = "worker" ]; then
          ${talosctlPath} gen config \
            --with-secrets ${talosOutputDir}/secrets.yaml \
            --config-patch-worker @${talosOutputDir}/patch-$i.json \
            --kubernetes-version $k8s_version \
            --output ${talosOutputDir}/$filename \
            --output-types worker \
            --force \
            vanillax-proxmox-talos https://${vip}:6443
        fi

        # Check if the output file was actually created
        if [ ! -f "${talosOutputDir}/$filename" ]; then
            echo "CRITICAL ERROR: talosctl failed to generate ${talosOutputDir}/$filename for node $hostname (role: $role)"
            echo "Contents of ${talosOutputDir}/patch-$i.json:"
            cat "${talosOutputDir}/patch-$i.json"
            exit 1 # Force the entire command to fail
        else
            echo "Successfully generated $filename for $hostname ($ip) with role $role"
        fi
    done
    `,
  triggers: [talosConfigFile.id]
});

// Configure talosctl endpoints using the generated files
const configureEndpoints = new command.local.Command("configure-endpoints", {
  create: pulumi.interpolate`
    # Ensure config files exist
    if [ ! -f "${talosOutputDir}/node-config.json" ]; then
        echo "Error: ${talosOutputDir}/node-config.json not found. This command depends on generate-node-configs."
        exit 1
    fi
    all_config_files=(${nodeConfig.map(n => `"${talosOutputDir}/${n.filename}"`).join(" ")})
    for file in "\${all_config_files[@]}"; do
        if [ ! -f "$file" ]; then
            echo "Error: Config file $file not found. This command depends on config generation."
            exit 1
        fi
    done

    export TALOSCONFIG=${talosOutputDir}/talosconfig
    control_plane_ips=(${nodeConfig.filter(n => n.role === 'controlplane').map(n => n.ip).join(" ")})
    echo "Configuring endpoints: \${control_plane_ips[@]}"
    ${talosctlPath} config endpoints \${control_plane_ips[@]}
    if [ $? -ne 0 ]; then echo "Error setting talosctl endpoints"; exit 1; fi

    echo "Configuring nodes: \${control_plane_ips[@]}"
    ${talosctlPath} config nodes \${control_plane_ips[@]}
    if [ $? -ne 0 ]; then echo "Error setting talosctl nodes"; exit 1; fi
    `,
  triggers: [generateNodeConfigs.id]
});

// Apply configurations to all nodes specified in nodeConfig
const applyConfigs = nodeConfig.map((node, i) =>
  new command.local.Command(`apply-config-${node.hostname}`, {
    create: pulumi.interpolate`
        export TALOSCONFIG=${talosOutputDir}/talosconfig
        echo "Attempting to apply config to node ${node.ip} (hostname: ${node.hostname}) using file ${talosOutputDir}/${node.filename}"
        ${talosctlPath} apply-config --insecure --nodes ${node.ip} --file ${talosOutputDir}/${node.filename}
        if [ $? -ne 0 ]; then
          echo "Error applying config to node ${node.ip} (hostname: ${node.hostname})"
          exit 1
        fi
        echo "Successfully applied config to node ${node.ip}"
        `,
    triggers: [configureEndpoints.id]
  })
);

// Bootstrap the cluster using the first control plane node IP
const bootstrapCluster = new command.local.Command("bootstrap-cluster", {
  create: pulumi.interpolate`
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    first_cp_node=${nodeConfig.find(n => n.role === 'controlplane')?.ip || ''}
    if [ -z "$first_cp_node" ]; then
        echo "Error: Could not find a control plane node IP for bootstrap."
        exit 1
    fi

    echo "Bootstrapping cluster on first node ($first_cp_node)..."

    ${talosctlPath} bootstrap --nodes $first_cp_node
    if [ $? -ne 0 ]; then
        echo "Error during bootstrap command for node $first_cp_node"
        exit 1
    fi

    echo "Waiting for API server to be available on $first_cp_node..."
    max_retries=30
    retry_interval=10
    for i in $(seq 1 $max_retries); do
        if ${talosctlPath} health --nodes $first_cp_node --server=false 2>/dev/null; then
            echo "API server is ready on $first_cp_node!"
            break
        fi
        if [ $i -eq $max_retries ]; then
            echo "Timed out waiting for API server on $first_cp_node after $(($max_retries * $retry_interval)) seconds."
            ${talosctlPath} health --nodes $first_cp_node --server=false
            exit 1
        fi
        echo "Waiting for API server on $first_cp_node... ($i/$max_retries)"
        sleep $retry_interval
    done
    `,
  triggers: applyConfigs.map(cmd => cmd.id)
});

// Wait for all nodes (control plane and workers) to join and be healthy
const waitForNodes = new command.local.Command("wait-for-nodes", {
  create: pulumi.interpolate`
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    first_cp_node=${nodeConfig.find(n => n.role === 'controlplane')?.ip || ''}
     if [ -z "$first_cp_node" ]; then
        echo "Error: Could not find a control plane node IP for health checks."
        exit 1
    fi

    echo "Waiting for all nodes to be ready (timeout 10m)..."

    ${talosctlPath} health --nodes $first_cp_node --server=false --wait-timeout=10m
    if [ $? -ne 0 ]; then
        echo "Error: Cluster did not become healthy within the timeout."
        ${talosctlPath} health --nodes $first_cp_node --server=false
        exit 1
    fi

    echo "Checking cluster membership..."
    all_nodes_ips=(${nodeConfig.map(n => n.ip).join(" ")})
    missing_nodes=0
    for ip in "\${all_nodes_ips[@]}"; do
        echo "Checking node $ip membership status..."
        if ! ${talosctlPath} get members --nodes $first_cp_node | grep -q $ip; then
            echo "ERROR: Node $ip not found in 'talosctl get members' output."
            missing_nodes=$((missing_nodes + 1))
        fi
    done

    if [ $missing_nodes -gt 0 ]; then
        echo "Error: $missing_nodes node(s) failed to join the cluster."
        exit 1
    fi

    echo "All nodes appear ready and are members."
    `,
  triggers: [bootstrapCluster.id]
});

// Get the kubeconfig
const kubeconfig = new command.local.Command("get-kubeconfig", {
  create: pulumi.interpolate`
    export TALOSCONFIG=${talosOutputDir}/talosconfig
    first_cp_node=${nodeConfig.find(n => n.role === 'controlplane')?.ip || ''}
     if [ -z "$first_cp_node" ]; then
        echo "Error: Could not find a control plane node IP to get kubeconfig."
        exit 1
    fi

    echo "Retrieving kubeconfig from $first_cp_node..."
    ${talosctlPath} --talosconfig=$TALOSCONFIG --nodes $first_cp_node kubeconfig ${talosOutputDir}/kubeconfig

    if [ -f "${talosOutputDir}/kubeconfig" ] && [ -s "${talosOutputDir}/kubeconfig" ]; then
        echo "Successfully generated kubeconfig at ${talosOutputDir}/kubeconfig"
    else
        echo "Failed to create a valid kubeconfig file at ${talosOutputDir}/kubeconfig"
        exit 1
    fi
    `,
  triggers: [waitForNodes.id]
});

// Install Cilium CNI with KubeProxy Replacement Enabled
const ciliumInstall = new command.local.Command("install-cilium", {
  create: pulumi.interpolate`
  echo "Waiting 15 seconds before installing Cilium..."
  sleep 15
  export KUBECONFIG=${talosOutputDir}/kubeconfig

  if [ ! -f "$KUBECONFIG" ]; then
      echo "Error: Kubeconfig file not found at $KUBECONFIG"
      exit 1
  fi

  echo "Applying PSA labels to kube-system..."
  kubectl label --overwrite namespace kube-system \
    pod-security.kubernetes.io/enforce=privileged \
    pod-security.kubernetes.io/audit=privileged \
    pod-security.kubernetes.io/warn=privileged
  if [ $? -ne 0 ]; then echo "Error applying PSA labels"; exit 1; fi


  echo "Adding Cilium Helm repo..."
  helm repo add cilium https://helm.cilium.io/
  if [ $? -ne 0 ]; then echo "Error adding Helm repo"; exit 1; fi

  echo "Updating Helm repos..."
  helm repo update
  if [ $? -ne 0 ]; then echo "Error updating Helm repos"; exit 1; fi

  echo "Installing/Upgrading Cilium with kubeProxyReplacement=strict..."
  helm upgrade --install cilium cilium/cilium \
    --version 1.17.3 \
    --namespace kube-system \
    --set ipam.mode=kubernetes \
    --set kubeProxyReplacement=strict \
    --set securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --set securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --set cgroup.autoMount.enabled=false \
    --set cgroup.hostRoot=/sys/fs/cgroup \
    --set apparmor.enabled=false \
    --set enableCriticalPriorityClass=false \
    --set priorityClassName=""
  if [ $? -ne 0 ]; then echo "Error installing/upgrading Cilium"; exit 1; fi

  echo "Verifying Cilium installation (waiting up to 5 minutes for pods)..."
  kubectl wait --for=condition=ready pod -l k8s-app=cilium -n kube-system --timeout=5m
  if [ $? -ne 0 ]; then
    echo "Error: Cilium pods did not become ready";
    kubectl -n kube-system get pods -l k8s-app=cilium
    kubectl -n kube-system describe pods -l k8s-app=cilium
    exit 1;
  fi

  echo "Cilium installation appears successful."
  kubectl -n kube-system get pods -l k8s-app=cilium
  `,
  triggers: [kubeconfig.id],
});

// Export the necessary information
export const talosconfigPath = pulumi.interpolate`${talosOutputDir}/talosconfig`;
export const kubeconfigPath = pulumi.interpolate`${talosOutputDir}/kubeconfig`;
export const clusterEndpoint = pulumi.interpolate`https://${vip}:6443`;