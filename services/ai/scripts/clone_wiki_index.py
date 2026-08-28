"""Copy the wiki vector index into a separate Pinecone index for UniPilot's use.

    python scripts/clone_wiki_index.py --source unipilot-wiki --target unipilot-wiki-app
    python scripts/clone_wiki_index.py --source unipilot-wiki --target unipilot-wiki-app --apply

DRY RUN BY DEFAULT.

## Why

`TymorIbrahim/unipilot-agent` is submitted coursework being graded, and it
retrieves from Pinecone index `unipilot-wiki`. UniPilot's `services/ai` reads
the same index, under the same (default) namespace -- and it does not only
read:

    wiki_index_sync.py:100   store.delete(stale)
    wiki_index_sync.py:134   store.upsert(...)

A sync run while developing UniPilot can therefore delete vectors the graded
agent needs to answer. That is a silent failure in the worst place: retrieval
returns fewer results, the agent answers from less context, and nothing errors.

## Why a separate index rather than a namespace

A namespace would isolate ordinary reads and writes -- every call in
`vector_store.py` already passes `namespace=self._namespace`. It would not
protect against a call that forgets to, or against `delete_all` on the index.
While the coursework is being graded, the cheap extra safety is worth having:
a separate index cannot be touched by any operation aimed at the original,
however it is spelled.

## No re-embedding

Vectors are fetched and re-upserted as they are. Embeddings are not recomputed,
so this costs nothing with the embedding provider -- which matters, because the
corpus is pinned to a specific model and re-embedding with a different one would
silently change retrieval quality rather than fail.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# `fetch()` passes ids in the query string and they are 64-char hashes, so a
# large batch overflows the URL. 25 keeps it under ~1.8KB.
BATCH = 25


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.environ.get("PINECONE_INDEX_NAME", "unipilot-wiki"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--namespace", default=os.environ.get("PINECONE_NAMESPACE", ""))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("PINECONE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("PINECONE_API_KEY is not set.")

    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=api_key)
    existing = [i["name"] for i in pc.list_indexes()]
    if args.source not in existing:
        raise SystemExit(f"source index {args.source!r} not found; have {existing}")

    source = pc.Index(args.source)
    stats = source.describe_index_stats()
    dimension = stats.get("dimension")
    total = stats.get("total_vector_count", 0)
    described = pc.describe_index(args.source)
    metric = getattr(described, "metric", None) or "cosine"

    print("source : %s  (%d vectors, dim %s, metric %s)" % (args.source, total, dimension, metric))
    print("target : %s%s" % (args.target, "" if args.apply else "   [DRY RUN -- nothing written]"))

    if not args.apply:
        print("\nDry run. Re-run with --apply to copy.")
        return

    if args.target not in existing:
        cloud = os.environ.get("PINECONE_CLOUD", "aws")
        region = os.environ.get("PINECONE_REGION", "us-east-1")
        print("creating %s (%s/%s)..." % (args.target, cloud, region))
        pc.create_index(
            name=args.target,
            dimension=dimension,
            metric=metric,
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        while not pc.describe_index(args.target).status.get("ready"):
            time.sleep(2)
        print("  ready")

    target = pc.Index(args.target)

    copied = 0
    ids_batch: list[str] = []
    for page in source.list(namespace=args.namespace or None):
        # `list()` yields ListResponse pages of ListItem objects, not strings;
        # passing those to fetch() serialises their repr into the URL.
        ids_batch.extend(getattr(item, "id", item) for item in page)
        while len(ids_batch) >= BATCH:
            chunk, ids_batch = ids_batch[:BATCH], ids_batch[BATCH:]
            copied += _copy(source, target, chunk, args.namespace)
            sys.stdout.write("\r  copied %d/%d" % (copied, total)); sys.stdout.flush()
    if ids_batch:
        copied += _copy(source, target, ids_batch, args.namespace)
    sys.stdout.write("\r  copied %d/%d\n" % (copied, total))

    time.sleep(5)
    after = target.describe_index_stats().get("total_vector_count", 0)
    print("\nverify: source %d, target %d -> %s" % (total, after, "match" if after == total else "MISMATCH"))


def _copy(source, target, ids: list[str], namespace: str) -> int:
    fetched = source.fetch(ids=ids, namespace=namespace or None)
    vectors = getattr(fetched, "vectors", None) or fetched.get("vectors", {})
    records = [
        {"id": vid, "values": v["values"] if isinstance(v, dict) else v.values,
         "metadata": (v.get("metadata") if isinstance(v, dict) else v.metadata) or {}}
        for vid, v in vectors.items()
    ]
    if records:
        target.upsert(vectors=records, namespace=namespace or None)
    return len(records)


if __name__ == "__main__":
    main()
