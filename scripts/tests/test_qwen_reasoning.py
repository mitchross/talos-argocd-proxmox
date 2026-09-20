"""Verify the client policy and deployed defaults without running an LLM."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'qwen_filter', ROOT / 'my-apps/ai/open-webui/qwen-no-think-filter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QwenReasoningTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, **options):
        return await module.Filter().inlet({'model': 'qwen3.8-27b', **options})

    def assert_mode(self, body, effort='xhigh', enabled=True, preserve=True):
        kwargs = body['chat_template_kwargs']
        self.assertIs(kwargs['enable_thinking'], enabled)
        self.assertIs(kwargs['preserve_thinking'], preserve)
        self.assertEqual(kwargs.get('reasoning_effort'), effort if enabled else None)
        self.assertEqual(kwargs, body['extra_body']['chat_template_kwargs'])
        self.assertEqual(body['reasoning_effort'], effort if enabled else None)
        self.assertEqual(body['extra_body']['reasoning_effort'], effort if enabled else None)
        expected = dict(temperature=1.0 if enabled else 0.7,
                        top_p=0.95 if enabled else 0.8, top_k=20, min_p=0.0,
                        presence_penalty=0.0 if enabled else 1.5,
                        repetition_penalty=1.05 if enabled else 1.0)
        for target in (body, body['extra_body']):
            self.assertEqual({key: target[key] for key in expected}, expected)
        if enabled:
            deployment = yaml.safe_load((ROOT / 'my-apps/ai/vllm/deployment.yaml').read_text())
            args = deployment['spec']['template']['spec']['containers'][0]['args']
            self.assertEqual(json.loads(args[args.index('--override-generation-config') + 1]), expected)

    async def test_default_request_has_explicit_xhigh_and_preserves_history(self):
        body = await self.request()
        self.assert_mode(body)
        self.assertEqual([body[k] for k in ['temperature', 'top_p', 'top_k',
                                          'min_p', 'presence_penalty', 'repetition_penalty']],
                         [1.0, 0.95, 20, 0.0, 0.0, 1.05])

    async def test_explicit_efforts_survive_both_forwarding_shapes(self):
        for effort in ['low', 'medium', 'xhigh']:
            for options in [dict(reasoning_effort=effort),
                            dict(chat_template_kwargs={'reasoning_effort': effort}),
                            dict(extra_body={'chat_template_kwargs': {'reasoning_effort': effort}})]:
                with self.subTest(effort=effort, options=options):
                    self.assert_mode(await self.request(**options), effort)

    async def test_stale_penalties_cannot_override_either_forwarding_shape(self):
        for effort in ('low', 'medium', 'xhigh', 'none'):
            for nested in (False, True):
                with self.subTest(effort=effort, nested=nested):
                    options = dict(repetition_penalty=1.2,
                                   extra_body={'repetition_penalty': 0.5})
                    (options['extra_body'] if nested else options)['reasoning_effort'] = effort
                    body = await self.request(**options)
                    enabled = effort != 'none'
                    self.assert_mode(body, effort, enabled=enabled, preserve=enabled)

    async def test_generic_high_maps_to_xhigh_and_invalid_effort_fails(self):
        for options in [dict(reasoning_effort='high'),
                        dict(chat_template_kwargs={'reasoning_effort': 'high'}),
                        dict(extra_body={'reasoning_effort': 'high'}),
                        dict(extra_body={'chat_template_kwargs': {'reasoning_effort': 'high'}})]:
            with self.subTest(options=options):
                self.assert_mode(await self.request(**options))
        with self.assertRaises(ValueError):
            await self.request(reasoning_effort='invented')

    async def test_empty_or_null_effort_uses_explicit_xhigh(self):
        for options in [dict(chat_template_kwargs={}), dict(reasoning_effort=None),
                        dict(extra_body={'chat_template_kwargs': {}}),
                        dict(extra_body={'reasoning_effort': None})]:
            with self.subTest(options=options):
                self.assert_mode(await self.request(**options))

    async def test_explicit_lower_effort_wins_conflicting_nested_default(self):
        for effort in ('low', 'medium'):
            body = await self.request(
                chat_template_kwargs={'reasoning_effort': effort},
                extra_body={'chat_template_kwargs': {'reasoning_effort': 'xhigh'}})
            self.assert_mode(body, effort)

    async def test_off_clears_effort_and_uses_non_thinking_sampler(self):
        body = await self.request(
            reasoning_effort='xhigh', temperature=1.0, top_p=0.95,
            chat_template_kwargs={'enable_thinking': False},
            extra_body={'reasoning_effort': 'high', 'temperature': 1.0})
        self.assert_mode(body, enabled=False, preserve=False)
        expected = dict(temperature=0.7, top_p=0.8, top_k=20, min_p=0.0,
                        presence_penalty=1.5, repetition_penalty=1.0)
        for key, value in expected.items():
            self.assertEqual(body[key], value)
            self.assertEqual(body['extra_body'][key], value)

    async def test_generic_none_means_explicit_off(self):
        for effort in ('none', 'off'):
            self.assert_mode(await self.request(reasoning_effort=effort), enabled=False, preserve=False)

    async def test_stateless_thinking_may_disable_preservation(self):
        body = await self.request(chat_template_kwargs={'preserve_thinking': False})
        self.assert_mode(body, preserve=False)

    async def test_tool_image_and_multiturn_payloads_are_preserved(self):
        messages = [
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,test'}}]},
            {'role': 'assistant', 'content': None, 'reasoning': 'Need the tool result.',
             'tool_calls': [{'id': 'call_1', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': '42'},
            {'role': 'user', 'content': 'Use the image and tool result.'},
        ]
        tools = [{'type': 'function', 'function': {'name': 'lookup', 'parameters': {'type': 'object'}}}]
        body = await self.request(messages=copy.deepcopy(messages), tools=copy.deepcopy(tools), tool_choice='auto')
        self.assert_mode(body)
        self.assertEqual(body['messages'], messages)
        self.assertEqual(body['tools'], tools)
        self.assertEqual(body['tool_choice'], 'auto')

    async def test_later_webui_defaults_cannot_restore_stale_effort(self):
        for selected in ['low', 'medium', 'xhigh', 'none']:
            body = await self.request(reasoning_effort=selected)
            for target in [body, body['extra_body']]:
                # WebUI fills missing model parameters after inlet filters.
                target.setdefault('reasoning_effort', 'high')
            self.assert_mode(body, selected, enabled=selected != 'none', preserve=selected != 'none')

    async def test_other_models_are_untouched(self):
        body = {'model': 'other-model', 'reasoning_effort': 'high', 'temperature': 0.2}
        before = copy.deepcopy(body)
        self.assertIs(await module.Filter().inlet(body), body)
        self.assertEqual(body, before)


class DeclaredPolicyTests(unittest.TestCase):
    def test_server_uses_explicit_xhigh_and_thinking_sampler(self):
        deployment = yaml.safe_load((ROOT / 'my-apps/ai/vllm/deployment.yaml').read_text())
        args = deployment['spec']['template']['spec']['containers'][0]['args']
        defaults = json.loads(args[args.index('--default-chat-template-kwargs') + 1])
        self.assertEqual(defaults, dict(enable_thinking=True, reasoning_effort='xhigh', preserve_thinking=True))
        sampler = json.loads(args[args.index('--override-generation-config') + 1])
        self.assertEqual(sampler, dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
                                      presence_penalty=0.0, repetition_penalty=1.05))

    def test_prefill_budget_cache_policy_and_allocator_are_explicit(self):
        deployment = yaml.safe_load((ROOT / 'my-apps/ai/vllm/deployment.yaml').read_text())
        container = deployment['spec']['template']['spec']['containers'][0]
        args = container['args']
        expected = {'--max-num-batched-tokens': '8192',
                    '--long-prefill-token-threshold': '4096',
                    '--max-num-seqs': '2', '--max-model-len': '262144',
                    '--mamba-cache-mode': 'align', '--prefix-match-unit': '16'}
        for flag, value in expected.items():
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertFalse(any(arg.startswith('--speculative-config') for arg in args))
        env = {entry['name']: entry.get('value') for entry in container['env']}
        self.assertEqual(env['PYTORCH_CUDA_ALLOC_CONF'], 'expandable_segments:True')

    def test_pi_mapping_exposes_only_valid_efforts_and_explicit_off(self):
        doc = (ROOT / 'docs/domains/ai-gpu/pi-agent-local-dev.md').read_text()
        configs = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', doc, re.S)]
        provider = next(c['providers']['vanillax-vllm'] for c in configs if 'providers' in c)
        compat = provider['compat']
        self.assertEqual(compat['thinkingFormat'], 'chat-template')
        self.assertFalse(compat['supportsReasoningEffort'])
        self.assertEqual(compat['chatTemplateKwargs']['preserve_thinking'], {'$var': 'thinking.enabled'})
        self.assertTrue(compat['chatTemplateKwargs']['reasoning_effort']['omitWhenOff'])
        mapping = provider['models'][0]['thinkingLevelMap']
        self.assertEqual({v for k, v in mapping.items() if k != 'off' and v is not None}, {'low', 'medium', 'xhigh'})
        settings = next(c for c in configs if 'defaultThinkingLevel' in c)
        self.assertEqual(settings['defaultThinkingLevel'], 'xhigh')
        self.assertEqual(settings['modelThinkingLevels']['vanillax-vllm/qwen3.8-27b'], 'xhigh')
        self.assertEqual(settings['modelThinkingLevels']['vanillax-openrouter/deepseek-flash'], 'high')
        self.assertIn('alias pi-qwen-only="pi --model $QWEN --thinking xhigh --models $QWEN"', doc)
        self.assertIn('alias pi-withflash="pi --model $AUTO --thinking medium --models $AUTO"', doc)

    def test_classifier_stays_off_and_cloud_efforts_do_not_follow_qwen(self):
        config = yaml.safe_load((ROOT / 'my-apps/ai/litellm/config.yaml').read_text())
        routes = {route['model_name']: route['litellm_params'] for route in config['model_list']}
        classifier = routes['pi-classifier']
        self.assertEqual(classifier['temperature'], 0)
        self.assertEqual(classifier['max_tokens'], 64)
        self.assertEqual(classifier['extra_body']['chat_template_kwargs'],
                         {'enable_thinking': False, 'preserve_thinking': False})
        local = routes['qwen3.8-27b-auto']
        self.assertNotIn('reasoning_effort', local)
        self.assertNotIn('chat_template_kwargs', local.get('extra_body', {}))
        tiers = routes['pi-auto']['complexity_router_config']['tier_model_configs']
        self.assertEqual(tiers['COMPLEX'][0]['litellm_params']['reasoning_effort'], 'high')
        self.assertEqual(tiers['REASONING'][0]['litellm_params']['reasoning_effort'], 'max')


if __name__ == '__main__':
    unittest.main()
