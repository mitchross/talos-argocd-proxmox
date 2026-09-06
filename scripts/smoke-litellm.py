#!/usr/bin/env python3
"""Send synthetic requests through LiteLLM; never print credentials or real chats.

Run in the LiteLLM container (it already has LITELLM_MASTER_KEY), or set that
variable and LITELLM_BASE_URL locally. This tests inference forwarding, not
PostHog ingestion: verify the marker in ClickHouse separately.
"""
import base64
import json
import os
import struct
import urllib.request
import uuid
import zlib

MARKER = 'ai-observability-' + uuid.uuid4().hex
BASE_URL = os.environ.get('LITELLM_BASE_URL', 'http://127.0.0.1:4000/v1').rstrip('/')
HEADERS = {'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY'],
           'Content-Type': 'application/json'}
BASE = {
    'model': 'qwen3.8-27b', 'max_tokens': 2048,
    'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0,
    'presence_penalty': 0.0, 'repetition_penalty': 1.0,
    'chat_template_kwargs': {'enable_thinking': True, 'preserve_thinking': True,
                            'reasoning_effort': 'medium'},
    'metadata': {'user_id': MARKER},
}


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def reasoning(message):
    return message.get('reasoning_content') or message.get('reasoning') or ''


def call(case, **options):
    payload = BASE | options
    request = urllib.request.Request(BASE_URL + '/chat/completions',
                                     data=json.dumps(payload).encode(), headers=HEADERS)
    with urllib.request.urlopen(request, timeout=300) as response:
        if payload.get('stream'):
            message = {'content': '', 'reasoning_content': ''}
            usage = None
            done = False
            for line in response:
                if not line.startswith(b'data: '):
                    continue
                data = line[6:].strip()
                if data == b'[DONE]':
                    done = True
                    break
                chunk = json.loads(data)
                if chunk.get('usage'):
                    usage = chunk['usage']
                for choice in chunk.get('choices', []):
                    delta = choice.get('delta', {})
                    message['content'] += delta.get('content') or ''
                    message['reasoning_content'] += reasoning(delta)
            check(done and usage, 'Stream must finish and include usage')
        else:
            result = json.load(response)
            check(result['choices'][0]['finish_reason'] != 'length', 'Output truncated')
            message = result['choices'][0]['message']
            usage = result.get('usage')
    check(usage and usage['total_tokens'] > 0, 'Missing token usage')
    print(json.dumps({'case': case, 'usage': usage, 'reasoning_chars': len(reasoning(message)),
                      'has_content': bool(message.get('content')),
                      'has_tool_calls': bool(message.get('tool_calls'))}), flush=True)
    return message


def main():
    print('PostHog distinct_id marker: ' + MARKER, flush=True)
    off = call('off', messages=[{'role': 'user', 'content': 'Reply: telemetry-ok'}],
               chat_template_kwargs={'enable_thinking': False, 'preserve_thinking': False},
               temperature=0.7, top_p=0.8, presence_penalty=1.5)
    check(not reasoning(off) and off.get('content'), 'Thinking-off response invalid')
    streamed = call('medium-stream', stream=True, stream_options={'include_usage': True},
                    messages=[{'role': 'user', 'content': 'What is 17 plus 25?'}])
    check(reasoning(streamed) and '42' in streamed['content'], 'Stream lost reasoning/content')
    messages = [{'role': 'user', 'content': 'Use lookup to find the value for key telemetry. Do not guess.'}]
    tools = [{'type': 'function', 'function': {
        'name': 'lookup', 'description': 'Look up an exact value.',
        'parameters': {'type': 'object', 'properties': {'key': {'type': 'string'}}, 'required': ['key']}}}]
    tool = call('medium-tool', messages=messages, tools=tools, tool_choice='auto')
    check(reasoning(tool) and tool.get('tool_calls'), 'Tool call/reasoning missing')
    check(tool['tool_calls'][0]['function']['name'] == 'lookup', 'Wrong tool')
    check(json.loads(tool['tool_calls'][0]['function']['arguments']) == {'key': 'telemetry'}, 'Invalid arguments')
    messages.extend([tool, {'role': 'tool', 'tool_call_id': tool['tool_calls'][0]['id'],
                            'content': 'telemetry-restored-42'}])
    reply = call('medium-tool-result', messages=messages, tools=tools)
    check('telemetry-restored-42' in (reply.get('content') or ''), 'Tool result lost in followup')

    def png_chunk(kind, data):
        return (struct.pack('!I', len(data)) + kind + data +
                struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff))

    # Synthetic solid red image; no user image is sent to telemetry.
    png = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('!2I5B', 32, 32, 8, 2, 0, 0, 0)) +
           png_chunk(b'IDAT', zlib.compress((b'\0' + b'\xff\0\0' * 32) * 32)) + png_chunk(b'IEND', b''))
    vision = call('medium-vision', messages=[{'role': 'user', 'content': [
        {'type': 'text', 'text': 'What color fills this image? Answer in one word.'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(png).decode()}}]}])
    check('red' in (vision.get('content') or '').lower(), 'Vision response invalid')
    print('PASS: off, streamed medium + usage, tool call, preserved followup, vision.')


if __name__ == '__main__':
    main()
