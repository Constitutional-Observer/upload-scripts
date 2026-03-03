#!/usr/bin/env python3
"""
Script to read documents from Meilisearch in chunks, apply embeddings, and update them.
"""

import argparse
import os
from typing import List, Dict, Any

from meilisearch import Client
from sentence_transformers import SentenceTransformer
from more_itertools import batched


def process_documents_in_batches(client: Client, index_name: str, model_name: str, batch_size: int = 50) -> None:
    """Process documents in batches: fetch, embed, update."""
    index = client.index(index_name)
    model = SentenceTransformer(model_name)

    offset = 0
    batch_num = 1
    
    while True:
        # Fetch batch
        print(f"Fetching batch {batch_num} (offset: {offset})...")
        batch = index.get_documents({"offset": offset, "limit": batch_size})

        if not batch.results:
            print("No more documents to process.")
            break

        documents = batch.results
        print(documents[0].__dict__)

        # Generate embeddings
        print(f"Generating embeddings for {len(documents)} documents...")
        texts = [doc.__dict__["__discussions"] for doc in documents]
        embeddings = model.encode(texts, batch_size=1, show_progress_bar=True)

        # Add embeddings to documents
        for i, doc in enumerate(documents):
            doc.embedding = embeddings[i].tolist()

        # Update documents
        print(f"Updating batch {batch_num}...")
        index.update_documents(documents)
        
        offset += batch_size
        batch_num += 1
        print(f"Completed batch {batch_num - 1}\n")


def main():
    parser = argparse.ArgumentParser(description="Update Meilisearch documents with embeddings.")
    parser.add_argument("--index", type=str, required=True, help="Meilisearch index name")
    parser.add_argument("--model", type=str, default="all-MiniLM-L6-v2", help="Sentence Transformer model name")
    parser.add_argument("--meilisearch-url", type=str, default="http://localhost:7700", help="Meilisearch URL")
    parser.add_argument("--meilisearch-key", type=str, default=None, help="Meilisearch API key")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing")
    
    args = parser.parse_args()
    
    # Initialize Meilisearch client
    client = Client(args.meilisearch_url, args.meilisearch_key)
    
    # Process documents in batches
    print(f"Starting to process documents from index: {args.index}")
    process_documents_in_batches(client, args.index, args.model, args.batch_size)
    
    print("All documents processed successfully!")


if __name__ == "__main__":
    main()
