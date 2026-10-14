"""Import public JSONL.zst annotations into the native vault without inventing full text."""
import argparse
import io
import json
import re
import sqlite3
from pathlib import Path

import zstandard

from ideascientist.utils.db import ensure_paper_full_text_schema


SCHEMA = '''
CREATE TABLE IF NOT EXISTS papers(id INTEGER PRIMARY KEY, title TEXT, authors TEXT, date TEXT, venue TEXT, source TEXT, url TEXT, abstract TEXT, arxiv_id TEXT UNIQUE, doi TEXT);
CREATE TABLE IF NOT EXISTS metadata_results_masked(paper_id INTEGER PRIMARY KEY, fields_json TEXT, model TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS public_proposals(paper_id INTEGER PRIMARY KEY, proposal_masked TEXT, split TEXT, generated_at TEXT);
CREATE TABLE IF NOT EXISTS import_progress(path TEXT PRIMARY KEY, rows INTEGER);
'''


def sections(text):
    parts = re.split(r'^##\s+(.+)\s*$', text, flags=re.MULTILINE)
    return {parts[i].strip().lower(): parts[i+1].strip() for i in range(1, len(parts)-1, 2)}


def import_records(records, db):
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    ensure_paper_full_text_schema(con)
    n = 0
    try:
        for r in records:
            cur = con.execute('INSERT OR IGNORE INTO papers(title,authors,date,venue,source,url,abstract,arxiv_id,doi) VALUES (?,?,?,?,?,?,?,?,?)', (r['title'], json.dumps(r.get('authors', [])), r['date'], '', 'SvalbardIdeaVault public annotation', r.get('arxiv_url',''), r.get('abstract',''), r['arxiv_id'], ''))
            if not cur.rowcount:
                continue
            pid = cur.lastrowid
            s = sections(r.get('proposal_masked', ''))
            fields = {'title': r['title'], 'problem_definition': r.get('problem_definition',''), 'core_problem': {'problem_statement': s.get('problem','')}, 'key_novelty': {'explanation': [r.get('intuition','')]}, 'method': {'high_level_flow': [s.get('method','')]}, 'limitations': [s.get('limitations','')], 'source_kind': 'public_results_masked_annotation'}
            con.execute('INSERT INTO metadata_results_masked VALUES (?,?,?,?)', (pid, json.dumps(fields, ensure_ascii=False), 'public_annotation_unknown_model', r.get('generated_at','')))
            con.execute('INSERT INTO public_proposals VALUES (?,?,?,?)', (pid, r.get('proposal_masked',''), r.get('split',''), r.get('generated_at','')))
            n += 1
        con.commit()
    finally:
        con.close()
    return n


def iter_records(path):
    with path.open('rb') as source, zstandard.ZstdDecompressor().stream_reader(source) as stream:
        for line in io.TextIOWrapper(stream, encoding='utf-8'):
            yield json.loads(line)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('data/SvalbardIdeaVault/records'))
    p.add_argument('--db', type=Path, default=Path('data/idea_vault.db'))
    p.add_argument('--limit', type=int, default=0, help='total input records; zero imports all')
    args = p.parse_args()
    seen = imported = 0
    for path in sorted(args.source.glob('*/*.jsonl.zst')):
        if args.db.exists() and not args.limit:
            with sqlite3.connect(args.db) as c:
                c.executescript(SCHEMA)
                if c.execute('SELECT 1 FROM import_progress WHERE path=?', (str(path),)).fetchone():
                    print('skip ' + str(path), flush=True)
                    continue
        batch = []
        file_rows = 0
        for record in iter_records(path):
            batch.append(record)
            seen += 1
            file_rows += 1
            if len(batch) >= 2000 or (args.limit and seen >= args.limit):
                imported += import_records(batch, args.db)
                batch.clear()
                print(f'processed {seen}, newly imported {imported}', flush=True)
            if args.limit and seen >= args.limit:
                break
        if batch:
            imported += import_records(batch, args.db)
        if not args.limit:
            with sqlite3.connect(args.db) as c:
                c.execute('INSERT OR REPLACE INTO import_progress VALUES (?,?)', (str(path), file_rows))
        if args.limit and seen >= args.limit:
            break
    print(f'import complete: {seen} input records, {imported} new records -> {args.db}', flush=True)


if __name__ == '__main__':
    main()
