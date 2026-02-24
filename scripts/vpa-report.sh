#!/bin/bash
# vpa-report.sh — Show VPA recommendations vs current resource requests
# Usage: ./scripts/vpa-report.sh [namespace]
# If no namespace given, shows all namespaces

set -euo pipefail

NS_FLAG=""
if [[ "${1:-}" != "" ]]; then
  NS_FLAG="-n $1"
else
  NS_FLAG="-A"
fi

echo "=========================================="
echo "  VPA Resource Recommendations Report"
echo "=========================================="
echo ""

# Get all VPAs with recommendations
kubectl get vpa $NS_FLAG -o json 2>/dev/null | python3 -c "
import json, sys

def bytes_to_human(b):
    \"\"\"Convert bytes string to human-readable.\"\"\"
    try:
        n = int(b)
    except (ValueError, TypeError):
        return str(b)
    if n >= 1073741824:
        return f'{n/1073741824:.1f}Gi'
    elif n >= 1048576:
        return f'{n/1048576:.0f}Mi'
    elif n >= 1024:
        return f'{n/1024:.0f}Ki'
    return str(n)

def cpu_to_milli(cpu):
    \"\"\"Normalize CPU to millicores string.\"\"\"
    if cpu is None:
        return '?'
    s = str(cpu)
    if s.endswith('m'):
        return s
    try:
        return f'{int(float(s) * 1000)}m'
    except ValueError:
        return s

data = json.load(sys.stdin)
items = data.get('items', [])

if not items:
    print('No VPA resources found.')
    sys.exit(0)

# Collect results
results = []
for vpa in items:
    ns = vpa['metadata']['namespace']
    name = vpa['metadata']['name']
    target_ref = vpa.get('spec', {}).get('targetRef', {})
    target_kind = target_ref.get('kind', '?')
    target_name = target_ref.get('name', '?')

    recs = vpa.get('status', {}).get('recommendation', {}).get('containerRecommendations', [])
    if not recs:
        results.append({
            'ns': ns, 'name': name, 'kind': target_kind,
            'container': '-', 'cpu_target': 'waiting...', 'mem_target': 'waiting...',
            'cpu_lower': '-', 'cpu_upper': '-',
            'mem_lower': '-', 'mem_upper': '-',
        })
        continue

    for rec in recs:
        target = rec.get('target', {})
        lower = rec.get('lowerBound', {})
        upper = rec.get('upperBound', {})
        results.append({
            'ns': ns,
            'name': name,
            'kind': target_kind,
            'container': rec.get('containerName', '?'),
            'cpu_target': cpu_to_milli(target.get('cpu')),
            'mem_target': bytes_to_human(target.get('memory', '?')),
            'cpu_lower': cpu_to_milli(lower.get('cpu')),
            'cpu_upper': cpu_to_milli(upper.get('cpu')),
            'mem_lower': bytes_to_human(lower.get('memory', '?')),
            'mem_upper': bytes_to_human(upper.get('memory', '?')),
        })

# Print table
fmt = '{:<20} {:<35} {:<25} {:>10} {:>10} {:>10} {:>10}'
print(fmt.format('NAMESPACE', 'WORKLOAD', 'CONTAINER', 'CPU TGT', 'CPU RANGE', 'MEM TGT', 'MEM RANGE'))
print('-' * 145)

# Sort by namespace then name
results.sort(key=lambda r: (r['ns'], r['name']))

for r in results:
    cpu_range = f'{r[\"cpu_lower\"]}-{r[\"cpu_upper\"]}'
    mem_range = f'{r[\"mem_lower\"]}-{r[\"mem_upper\"]}'
    print(fmt.format(
        r['ns'][:20],
        f'{r[\"kind\"]}/{r[\"name\"]}'[:35],
        r['container'][:25],
        r['cpu_target'],
        cpu_range[:10],
        r['mem_target'],
        mem_range[:10],
    ))

print()
print(f'Total: {len(results)} containers with VPA recommendations')
print()
print('Legend:')
print('  CPU TGT  = recommended CPU request (millicores)')
print('  MEM TGT  = recommended memory request')
print('  RANGE    = lowerBound-upperBound')
print()
print('Action needed if your current request is:')
print('  < lowerBound  →  INCREASE NOW (pod is being throttled)')
print('  < target      →  INCREASE (under-provisioned)')
print('  ≈ target      →  KEEP (well-tuned)')
print('  > 2x target   →  DECREASE (over-provisioned)')
"
