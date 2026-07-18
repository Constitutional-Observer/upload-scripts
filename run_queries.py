"""
Script to run a sequence of queries on an index, and store the results

The results can then be used for comparison
"""

import argparse
import json

import httpx
import meilisearch
import pandas as pd
import yaml


def query_meilisearch(
    query: str,
    index_name: str,
    client: meilisearch.Client,
    limit: int = 20,
    hybrid_search: bool = False,
) -> dict:
    """Run a query and return full results including documents"""
    search_params = {
        "limit": limit,
        "attributesToRetrieve": ["*"],  # Get all fields for NDCG evaluation
        "showRankingScore": True,  # Include ranking scores
        "showRankingScoreDetails": True,  # Include detailed ranking info
    }

    if hybrid_search:
        search_params["hybrid"] = {"embedder": "LLAMA_JINA_PROVIDER"}

    results = client.get_index(index_name).search(query, search_params)
    return results


def get_index_metadata(
    index_name: str,
    client: meilisearch.Client,
    meilisearch_url: str = None,
    api_key: str = None,
) -> dict:
    """Get metadata about the index settings at the time of query"""
    index = client.get_index(index_name)

    # Get the raw HTTP connection details for direct requests when needed
    # (for embedders which has deserialization issues in the client)
    if meilisearch_url is None or api_key is None:
        meilisearch_url = client._http._base_url
        api_key = client._http._headers.get("Authorization", "").replace("Bearer ", "")

    metadata = {
        "index_name": index_name,
        "index_uid": index.uid,
        "primary_key": index.get_primary_key(),
        "created_at": index.created_at,
        "updated_at": index.updated_at,
    }

    # Get embedders info - use direct HTTP call to bypass deserialization bugs
    index_uid = index.uid
    settings_url = f"{meilisearch_url}/indexes/{index_uid}/settings"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = httpx.get(settings_url, headers=headers, timeout=30.0)
    response.raise_for_status()
    # Store the raw JSON response as-is
    metadata["settings"] = response.json()

    # Get stats
    stats = index.get_stats()
    # Convert stats to a plain dict, handling nested FieldDistribution objects
    metadata["stats"] = {
        "number_of_documents": getattr(stats, "number_of_documents", 0),
        "is_indexing": getattr(stats, "is_indexing", False),
        "field_distribution": getattr(stats, "field_distribution", {}),
    }

    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("meilisearch_config")
    parser.add_argument(
        "queries_file", help="CSV file with 'primary_search' and 'related' columns"
    )
    parser.add_argument(
        "output_file", help="File to store query results in JSON format"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results per query (default: 20)",
    )
    parser.add_argument(
        "--state-code",
        help="State code to use for looking up index name in config (e.g., 'KA', 'AP')",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        default=False,
        help="Enable hybrid search with embeddings (default: False)",
    )
    args = parser.parse_args()

    with open(args.meilisearch_config) as f:
        config = yaml.safe_load(f)

    # Determine index name - from argument, config with state code, or config global
    index_name = config["index_config"][args.state_code]["index_name"]
    if index_name is None:
        parser.error("index_name must be provided in config file")

    client = meilisearch.Client(
        config["connection"]["URL"], config["connection"]["API_KEY"]
    )
    client.health()

    # Read queries from CSV file
    df = pd.read_csv(args.queries_file, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    related_map = dict(
        zip(
            df["primary_search"].astype(str).str.strip(),
            df["related"].astype(str).str.strip(),
        )
    )

    # Get index metadata once at the start (settings are consistent across all queries in a run)
    print(f"Collecting index metadata for {index_name}...")
    index_metadata = get_index_metadata(
        index_name, client, config["connection"]["URL"], config["connection"]["API_KEY"]
    )

    # Add query run metadata
    query_run_metadata = {
        "hybrid_search_enabled": args.hybrid,
        "limit": args.limit,
        "state_code": args.state_code,
        "timestamp": pd.Timestamp.now().isoformat(),
        "meilisearch_url": config["connection"]["URL"],
    }

    # Run queries and store results
    results = []
    for query in df["primary_search"].astype(str).str.strip():
        print(f"Running query: {query}")
        query_results = query_meilisearch(
            query, index_name, client, args.limit, args.hybrid
        )

        # Store full results including hits (actual documents) for NDCG calculation
        result_entry = {
            "query": query,
            "related_terms": related_map.get(query, ""),
            "hits": json.dumps(query_results.get("hits", [])),
            "processing_time_ms": query_results.get("processingTimeMs"),
            "total_hits": query_results.get("estimatedTotalHits", 0),
            "limit": query_results.get("limit"),
            "offset": query_results.get("offset"),
        }
        results.append(result_entry)

    results_df = pd.DataFrame(results)

    results_df.to_parquet(args.output_file)
    print(f"Results saved to {args.output_file}")
    print(f"Processed {len(results)} queries")

    # Save metadata to a sidecar JSON file
    metadata_file = args.output_file + ".metadata.json"
    combined_metadata = {
        "index_metadata": index_metadata,
        "query_run_metadata": query_run_metadata,
    }
    with open(metadata_file, "w") as f:
        json.dump(combined_metadata, f, indent=2, default=str)
    print(f"Metadata saved to {metadata_file}")


if __name__ == "__main__":
    main()
