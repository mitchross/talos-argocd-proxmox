"""Guard the INT4 cutover, native context, vision, and retained rollback manifest."""
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'my-apps/ai/vllm'


def test_dualfast_render_uses_pinned_int4_manifest_and_preserves_fp8():
    docs = list(yaml.safe_load_all(subprocess.check_output(
        ['kubectl', 'kustomize', str(APP)], text=True)))
    deployment = next(d for d in docs if d['kind'] == 'Deployment')
    pod = deployment['spec']['template']['spec']
    server = pod['containers'][0]
    args = server['args']
    config = next(d for d in docs if d['kind'] == 'ConfigMap' and 'model-manifest.json' in d.get('data', {}))
    manifest = json.loads(config['data']['model-manifest.json'])
    assert manifest['repo'] == 'Frozenlock/Qwen3.8-27B-int4-AutoRound'
    assert manifest['revision'] == 'b4c61732c4f2d8af323d75ba5702b5c7f3361539'
    assert args[0] == '/models/' + manifest['directory']
    assert json.loads((APP / 'model-manifest.json').read_text())['repo'] == 'Qwen/Qwen3.8-27B-FP8'
    files = {f['name'] for f in manifest['files']}
    assert {'config.json', 'chat_template.jinja', 'preprocessor_config.json',
            'processor_config.json', 'model.safetensors.index.json'} <= files
    assert sum(f['size'] for f in manifest['files']) == 19_016_926_426
    assert all(len(f['sha256']) == 64 for f in manifest['files'])
    assert deployment['spec']['replicas'] == 1
    assert server['resources']['limits']['nvidia.com/gpu'] == '2'
    assert args[args.index('--quantization') + 1] == 'auto_round'
    assert args[args.index('--max-model-len') + 1] == '262144'
    assert args[args.index('--gpu-memory-utilization') + 1] == '0.90'
    assert args[args.index('--max-num-seqs') + 1] == '16'
    assert args[args.index('--mamba-ssm-cache-dtype') + 1] == 'bfloat16'
    assert '--speculative-config' not in args
    assert '--language-model-only' not in args
    assert not any('rope' in arg.lower() or 'yarn' in arg.lower() for arg in args)
    assert server['image'] == 'ghcr.io/mitchross/vllm-qwen38-dualfast:0.32.0-dualfast.2'
    assert args[args.index('--chat-template') + 1] == '/etc/club3090/qwen38-reasoning-effort-template/chat_template.jinja'
    assert json.loads(args[args.index('--default-chat-template-kwargs') + 1]) == {
        'enable_thinking': True, 'reasoning_effort': 'medium', 'preserve_thinking': True}
    assert args[args.index('--reasoning-parser') + 1] == 'qwen3'
    env = {e['name']: e['value'] for e in server['env']}
    assert json.loads(env['CLUB3090_REASONING_EFFORT_BUDGETS']) == {
        'minimal': 4096, 'low': 4096, 'medium': 16384,
        'high': 32768, 'xhigh': 32768, 'max': 32768}
    assert env['CLUB3090_DEFAULT_THINKING_TOKEN_BUDGET'] == '16384'
    assert env['VLLM_MARLIN_INPUT_DTYPE'] == 'int8'
    assert env['VLLM_USE_FLASHINFER_SAMPLER'] == '0'
    assert env['NCCL_P2P_DISABLE'] == '1'
    assert env['NCCL_CUMEM_ENABLE'] == '0'
    assert next(v for v in pod['volumes'] if v['name'] == 'repo-scripts')['configMap']['name'] == config['metadata']['name']
    assert pod['initContainers'][0]['command'][-1] == 'wait'


def test_strata_replica_override_is_parked():
    docs = list(yaml.safe_load_all(subprocess.check_output(
        ['kubectl', 'kustomize', str(ROOT / 'my-apps/ai/strata')], text=True)))
    assert next(d for d in docs if d['kind'] == 'Deployment')['spec']['replicas'] == 0
