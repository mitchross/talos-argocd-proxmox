#!/usr/bin/env python3
"""Verify the installed LiteLLM OTel adapter using synthetic in-memory spans.

Run inside the pinned LiteLLM container. No credentials, LLM calls or telemetry
exports are used. This verifies adapter compatibility, not Langfuse delivery.
"""
import base64

from litellm import ModelResponse
from litellm.integrations.langfuse.langfuse_otel import LangfuseOtelLogger
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def main():
    config = LangfuseOtelLogger._build_langfuse_otel_config(
        'synthetic-public', 'synthetic-secret', 'http://langfuse-web.langfuse.svc.cluster.local:3000')
    assert config.endpoint == 'http://langfuse-web.langfuse.svc.cluster.local:3000/api/public/otel'
    assert 'x-langfuse-ingestion-version=4' in config.headers
    auth = base64.b64encode(b'synthetic-public:synthetic-secret').decode()
    assert 'Authorization=Basic ' + auth in config.headers

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    kwargs = {
        'model': 'qwen3.8-27b',
        'messages': [{'role': 'user', 'content': 'synthetic'}],
        'litellm_params': {'metadata': {'session_id': 'synthetic-session',
                                      'trace_name': 'smoke', 'generation_name': 'medium-tool'}},
        'standard_logging_object': {'model': 'qwen3.8-27b', 'response_cost': 0.0,
                                    'model_parameters': {}, 'metadata': {}},
    }
    response = ModelResponse(
        model='qwen3.8-27b',
        choices=[{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'test', 'type': 'function',
             'function': {'name': 'lookup', 'arguments': '{"key":"test"}'}}]}}],
        usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15})
    with provider.get_tracer('synthetic').start_as_current_span('synthetic') as span:
        LangfuseOtelLogger.set_langfuse_otel_attributes(span, kwargs, response)
    attributes = exporter.get_finished_spans()[0].attributes
    assert attributes['langfuse.observation.type'] == 'generation'
    assert attributes['session.id'] == 'synthetic-session'
    assert 'lookup' in attributes['langfuse.observation.output']
    assert attributes['llm.token_count.prompt'] == 10
    assert attributes['llm.token_count.completion'] == 5
    assert attributes['llm.token_count.total'] == 15
    assert attributes['llm.cost.total'] == 0.0
    provider.shutdown()
    print('PASS: v4 endpoint/header/auth, session grouping, tool output, token usage and zero local cost')


if __name__ == '__main__':
    main()
