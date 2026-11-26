# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json

import httpx
import pytest

from common.llm.provider.generic_llm import GenericLLM


def event(content=None, reason=None):
    return 'data: ' + json.dumps({'choices': [{'delta': {'content': content}, 'finish_reason': reason}]}) + '\n\n'


@pytest.fixture
def client():
    llm = GenericLLM({'url': 'https://synthetic.invalid/chat', 'stream': True,
                      'response': {'answer': 'choices[0].message.content', 'reasoning': 'choices[0].message.reasoning_content'}})
    llm._client.close()
    yield llm
    llm._client.close()


def respond(client, text, content_type='text/event-stream'):
    requests = []
    def send(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={'content-type': content_type}, text=text)
    client._client = httpx.Client(transport=httpx.MockTransport(send))
    return requests


@pytest.mark.parametrize('text', [
    event('partial'),
    event('cut', 'length') + 'data: [DONE]\n\n',
    event('blocked', 'content_filter') + 'data: [DONE]\n\n',
    event('partial') + 'data: {"error":{"message":"provider error"}}\n\ndata: [DONE]\n\n',
    'data: {"error":{"message":"provider error"}}\n\ndata: [DONE]\n\n',
    'data: invalid-json\n\ndata: [DONE]\n\n',
    event(None, 'stop'),
])
def test_incomplete_or_failed_stream_is_not_a_normal_answer(client, text):
    respond(client, text)
    with pytest.raises(RuntimeError, match='LLM call failed'):
        client.ask_llm('synthetic prompt')


@pytest.mark.parametrize('suffix', [event(None, 'stop'), 'data: [DONE]\n\n', event(None, 'stop') + 'data: [DONE]\n\n'])
def test_complete_stream_supports_stop_or_done(client, suffix):
    requests = respond(client, ': heartbeat\n\n' + event('answer') + suffix)
    assert client.ask_llm('synthetic prompt') == ('', 'answer')
    assert requests[0]['stream'] is True


def test_stream_response_must_be_sse(client):
    respond(client, '{"choices":[{"message":{"content":"answer"}}]}', 'application/json')
    with pytest.raises(RuntimeError, match='non-SSE'):
        client.ask_llm('synthetic')


def test_conflicting_body_stream_rejected_before_network(client):
    requests = respond(client, event('answer', 'stop'))
    client._body_template = {'stream': False}
    with pytest.raises(RuntimeError, match='conflicts'):
        client.ask_llm('synthetic')
    assert requests == []


def test_multiline_sse_and_reasoning_are_reassembled(client):
    payload = 'data: {"choices": [\ndata: {"delta": {"content": "answer", "reasoning_content": "reason"}}]}\n\n'
    respond(client, payload + event(None, 'stop'))
    assert client.ask_llm('synthetic') == ('reason', 'answer')
