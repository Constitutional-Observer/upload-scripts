#!/usr/bin/env python3
"""
Script to read documents from Meilisearch in chunks, apply embeddings, and update them.
"""

import os
import argparse

import httpx
from meilisearch import Client


def process_documents_in_batches(
    client: Client, index_name: str, batch_size: int = 50
) -> None:
    """Process documents in batches: fetch, embed, update."""
    index = client.index(index_name)

    # offset = 0
    # batch_num = 1

    # llama_client = httpx.Client()
    result = index.update_embedders(
        {
            "LLAMA_JINA_PROVIDER": {
                "source": "rest",
                "dimensions": 768,
                "url": "http://100.87.243.70:10000/embeddings",
                "request": {
                    "model": "jinaai/jina-embeddings-v5-text-nano-retrieval",
                    "input": ["{{text}}"],
                },
                "response": [{"embedding": ["{{embedding}}"]}],
                "documentTemplate": "Document: {{doc.__discussions}}",
            }
        }
    )
    print(result.task_uid)
    print(result)

    # while True:
    #     # Fetch batch
    #     print(f"Fetching batch {batch_num} (offset: {offset})...")
    #     batch = index.get_documents({"offset": offset, "limit": batch_size})

    #     if not batch.results:
    #         print("No more documents to process.")
    #         break

    #     documents = batch.results

    #     # Generate embeddings
    #     print(f"Generating embeddings for {len(documents)} documents...")
    #     texts = ["Document: " + doc.__dict__["__discussions"] for doc in documents]
    #     embeddings = llama_client.post(url=f"{LLAMA_CPP_URL}/v1/embeddings", json={"input": texts}, timeout=20)

    #     # Add embeddings to documents
    #     for i, doc in enumerate(documents):
    #         doc.__dict__["_vectors"] = {"hf-provider": embeddings.json()["data"][i]["embedding"]}

    #     # Update documents
    #     print(f"Updating batch {batch_num}...")
    #     result = index.update_documents([d.__dict__ for d in documents])
    #     print(result.task_uid)
    #
    #     offset += batch_size
    #     batch_num += 1
    #     print(f"Completed batch {batch_num - 1}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Update Meilisearch documents with embeddings."
    )
    parser.add_argument(
        "--index", type=str, required=True, help="Meilisearch index name"
    )
    parser.add_argument(
        "--meilisearch-url",
        type=str,
        default="http://localhost:7700",
        help="Meilisearch URL",
    )
    parser.add_argument(
        "--meilisearch-key", type=str, default=None, help="Meilisearch API key"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Batch size for processing"
    )

    args = parser.parse_args()

    # Initialize Meilisearch client
    client = Client(args.meilisearch_url, args.meilisearch_key)

    # Process documents in batches
    print(f"Starting to process documents from index: {args.index}")
    process_documents_in_batches(client, args.index, args.batch_size)

    print("All documents processed successfully!")


if __name__ == "__main__":
    main()
