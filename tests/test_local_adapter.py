import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
import asyncio
import hashlib
from types import SimpleNamespace
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests
from pathlib import Path
from unittest.mock import patch


class AdapterTests(unittest.TestCase):
    def test_rate_gate_spaces_calls_and_respects_deadline(self):
        from ideascientist.serving.codex_bridge import RateGate
        gate = RateGate(0.02)
        gate.wait(time.monotonic()+1)
        first = time.monotonic()
        gate.wait(time.monotonic()+1)
        self.assertGreaterEqual(time.monotonic()-first, 0.019)
        gate.defer(0.04)
        with self.assertRaises(TimeoutError):
            gate.wait(time.monotonic()+0.01)

    def test_cli_rate_limit_recovers_before_returning_completion(self):
        from ideascientist.serving import codex_bridge as bridge
        def process(cmd, **kwargs):
            if 'login' in cmd:
                return SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr='')
            process.n += 1
            if process.n == 1:
                return SimpleNamespace(returncode=1, stdout='{"type":"error","message":"429 Too Many Requests"}', stderr='')
            Path(cmd[cmd.index('-o')+1]).write_text('{"content":"recovered","tool_calls":[]}')
            return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}', stderr='')
        process.n = 0
        with patch('subprocess.run', side_effect=process), patch.object(bridge, '_gate', bridge.RateGate(0)), patch.dict(os.environ, {'CODEX_BRIDGE_RATE_BACKOFF': '0'}):
            answer = bridge.infer({'messages': [{'role':'user','content':'test'}]})
            self.assertEqual(answer['choices'][0]['message']['content'], 'recovered')

    def test_cli_failure_surfaces_json_event_error(self):
        from ideascientist.serving.codex_bridge import cli_failure
        result = SimpleNamespace(stdout='{"type":"turn.failed","error":{"message":"connection closed before completion"}}\n', stderr='irrelevant warning')
        self.assertIn('connection closed before completion', cli_failure(result))

    def test_chat_recovers_from_transient_502(self):
        from ideascientist.harness.client import AgenticLLMClient
        class Endpoint(BaseHTTPRequestHandler):
            calls = 0
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                type(self).calls += 1
                status = 502 if self.calls == 1 else 200
                body = {'error': {'message': 'temporary failure'}} if status == 502 else {'choices': [{'message': {'role': 'assistant', 'content': 'recovered'}}], 'usage': {}}
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Endpoint)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as d, patch('time.sleep'):
                client = AgenticLLMClient(api_key='EMPTY', model='codex-cli', base_url=f'http://127.0.0.1:{server.server_port}/v1', log_dir=d)
                try:
                    result = client.chat([{'role':'user','content':'test'}], max_retries=2)
                    self.assertEqual(result['choices'][0]['message']['content'], 'recovered')
                    self.assertEqual(Endpoint.calls, 2)
                finally:
                    client.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_two_inference_requests_can_progress_concurrently(self):
        from ideascientist.serving import codex_bridge as bridge
        barrier = threading.Barrier(2, timeout=5)
        def inference(request):
            barrier.wait()
            return bridge.completion({'content': 'ok', 'tool_calls': []}, request, {})
        server = ThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.object(bridge, 'infer', side_effect=inference), ThreadPoolExecutor(max_workers=2) as pool:
                url = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
                futures = [pool.submit(requests.post, url, json={'messages': []}, timeout=7) for _ in range(2)]
                responses = [f.result(timeout=8) for f in futures]
                self.assertEqual([r.status_code for r in responses], [200, 200])
                self.assertTrue(all(r.json()['choices'][0]['message']['content'] == 'ok' for r in responses))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_dispatch_cannot_exceed_bridge_capacity(self):
        from ideascientist.serving.codex_bridge import completion
        payload = {'tools': [{'type': 'function', 'function': {'name': 'spawn_subagent'}}]}
        call = {'name': 'spawn_subagent', 'arguments': '{}'}
        with self.assertRaises(ValueError):
            completion({'content': '', 'tool_calls': [call] * 5}, payload, {})

    def test_hashing_does_not_require_python311(self):
        spec = importlib.util.spec_from_file_location('downloader', Path(__file__).resolve().parents[1]/'scripts/download_public_vault.py')
        module = importlib.util.module_from_spec(spec)
        # Imports must not start network downloads.
        with patch('subprocess.run', side_effect=AssertionError('unexpected download')):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'data'
            p.write_bytes(b'hello')
            with patch.object(hashlib, 'file_digest', None, create=True):
                self.assertEqual(module.sha256_file(p), hashlib.sha256(b'hello').hexdigest())

    def test_api_key_login_is_rejected(self):
        from ideascientist.serving.codex_bridge import require_chatgpt_login
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Logged in using an API key', stderr='')):
            with self.assertRaises(RuntimeError):
                require_chatgpt_login()
        with patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='Logged in using ChatGPT', stderr='')):
            require_chatgpt_login()

    def test_orchestrator_reader_writes_digest(self):
        from ideascientist.harness import runner
        class Client:
            last_prompt_tokens = 0
            def __init__(self, **kwargs): pass
            def set_step(self, value): pass
            def chat(self, *args, **kwargs):
                return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1', 'function': {'name': 'spawn_subagent', 'arguments': '{"role":"gap_finder","task":"read paper"}'}}]}}]}
            def summary(self): return {'total_tokens': 0, 'total_calls': 1}
            def close(self): pass
        def subrole(role, task, ctx, *args, **kwargs):
            digest = ctx.reader_fn(1, ['explain method'])
            return {'role': role, 'digest': digest, 'tokens': 0, 'calls': 0}
        with tempfile.TemporaryDirectory() as d, patch.object(runner, 'AgenticLLMClient', Client), patch.object(runner, '_run_subagent', side_effect=subrole), patch.object(runner, 'read_paper_single_turn', return_value='A grounded digest'):
            asyncio.run(runner.run_ideation('research problem', d, model='codex-cli', max_turns=1))
            self.assertEqual((Path(d)/'outputs/papers/1.md').read_text().strip(), 'A grounded digest')

    def test_adapter_modules_exist(self):
        self.assertIsNotNone(importlib.util.find_spec('ideascientist.serving.codex_bridge'))
        self.assertIsNotNone(importlib.util.find_spec('ideascientist.vault.import_public'))

    def test_tool_roundtrip_and_reject_unknown(self):
        from ideascientist.serving.codex_bridge import completion
        payload = {'tools': [{'type': 'function', 'function': {'name': 'keyword_search'}}]}
        result = completion({'content': '', 'tool_calls': [{'name': 'keyword_search', 'arguments': '{"queries":["memory"]}'}]}, payload, {})
        call = result['choices'][0]['message']['tool_calls'][0]
        self.assertEqual(json.loads(call['function']['arguments']), {'queries': ['memory']})
        with self.assertRaises(ValueError):
            completion({'content': '', 'tool_calls': [{'name': 'shell', 'arguments': '{}'}]}, payload, {})
        with self.assertRaises(ValueError):
            completion({'content': '', 'tool_calls': [{'name': 'keyword_search', 'arguments': 'broken'}]}, payload, {})

    def test_public_record_is_readable_without_fake_fulltext(self):
        from ideascientist.vault.import_public import import_records
        from ideascientist.harness import corpus, runner
        record = {'arxiv_id': '2501.00001', 'title': 'Memory retrieval', 'authors': ['A'], 'date': '2025-01-01', 'arxiv_url': 'https://arxiv.org/abs/2501.00001', 'abstract': 'Memory retrieval method.', 'problem_definition': 'Retrieve task memories.', 'intuition': 'Rank by relevance.', 'proposal_masked': '## Problem\nOld retrieval wastes tokens.\n\n## Method\nRank stored memories.\n', 'split': 'corpus', 'generated_at': ''}
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'vault.db'
            self.assertEqual(import_records([record], db), 1)
            self.assertEqual(import_records([record], db), 0)
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM paper_full_text').fetchone()[0], 0)
                pid = c.execute('SELECT id FROM papers').fetchone()[0]
            with patch.dict(os.environ, {'IDEA_VAULT_DB': str(db), 'IDEASCIENTIST_READER_FULLTEXT_TOK_CAP': '0'}):
                self.assertEqual(corpus.get_paper_biblio(pid)['arxiv_id'], '2501.00001')
                text = corpus.get_stored_full_text(pid)
                self.assertIn('ANNOTATION', text)
                self.assertIn('Rank stored memories.', text)
                self.assertIn('Rank stored memories.', runner.build_reader_task(pid, ['Explain the method']))

    def test_cutoff_excludes_future_papers(self):
        from ideascientist.vault.import_public import import_records
        from ideascientist.vault.index import build_keyword_index
        from ideascientist.harness import corpus
        def rec(i, date):
            return dict(arxiv_id=i, title=f'Memory {i}', date=date, abstract='memory', proposal_masked='memory retrieval', problem_definition='memory retrieval', intuition='memory', authors=[], split='corpus')
        with tempfile.TemporaryDirectory() as d:
            db, index = Path(d)/'vault.db', Path(d)/'keyword.db'
            import_records([rec('2501.00001','2025-01-01'), rec('2601.00001','2026-01-01')], db)
            build_keyword_index(db, index, n_readers=1)
            with patch.dict(os.environ, {'IDEA_VAULT_DB': str(db), 'IDEASCIENTIST_KEYWORD_INDEX': str(index)}):
                corpus._KW_VALIDATED = False
                results = corpus.keyword_search(['memory'])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]['title'], 'Memory 2501.00001')

if __name__ == '__main__':
    unittest.main()
