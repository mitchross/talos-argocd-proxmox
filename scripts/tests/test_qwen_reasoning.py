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

    def assert_mode(self, body, effort='medium', enabled=True, preserve=True):
        kwargs = body['chat_template_kwargs']
        self.assertIs(kwargs['enable_thinking'], enabled)
        self.assertIs(kwargs['preserve_thinking'], preserve)
        self.assertEqual(kwargs.get('reasoning_effort'), effort if enabled else None)
        self.assertEqual(kwargs, body['extra_body']['chat_template_kwargs'])
        self.assertEqual(body['reasoning_effort'], effort if enabled else None)
        self.assertEqual(body['extra_body']['reasoning_effort'], effort if enabled else None)

    async def test_default_request_has_explicit_medium_and_preserves_history(self):
        body = await self.request()
        self.assert_mode(body)
        self.assertEqual([body[k] for k in ['temperature', 'top_p', 'top_k',
                                          'min_p', 'presence_penalty', 'repetition_penalty']],
                         [1.0, 0.95, 20, 0.0, 0.0, 1.0])

    async def test_explicit_efforts_survive_both_forwarding_shapes(self):
        for effort in ['low', 'medium', 'xhigh']:
            for options in [dict(reasoning_effort=effort),
                            dict(chat_template_kwargs={'reasoning_effort': effort}),
                            dict(extra_body={'chat_template_kwargs': {'reasoning_effort': effort}})]:
                with self.subTest(effort=effort, options=options):
                    self.assert_mode(await self.request(**options), effort)

    async def test_generic_high_maps_to_medium_and_invalid_effort_fails(self):
        self.assert_mode(await self.request(reasoning_effort='high'))
        with self.assertRaises(ValueError):
            await self.request(reasoning_effort='invented')

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
        self.assert_mode(await self.request(reasoning_effort='none'), enabled=False, preserve=False)

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
    def test_server_cannot_use_implicit_xhigh_or_non_thinking_sampler(self):
        deployment = yaml.safe_load((ROOT / 'my-apps/ai/vllm/deployment.yaml').read_text())
        args = deployment['spec']['template']['spec']['containers'][0]['args']
        defaults = json.loads(args[args.index('--default-chat-template-kwargs') + 1])
        self.assertEqual(defaults, dict(enable_thinking=True, reasoning_effort='medium', preserve_thinking=True))
        sampler = json.loads(args[args.index('--override-generation-config') + 1])
        self.assertEqual(sampler, dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
                                      presence_penalty=0.0, repetition_penalty=1.0))

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
        self.assertEqual(settings['defaultThinkingLevel'], 'medium')
        self.assertEqual(settings['modelThinkingLevels']['vanillax-vllm/qwen3.8-27b'], 'medium')


if __name__ == '__main__':
    unittest.main()
