"""
Script to run a sequence of queries on an index, and store the results

The results can then be used for comparison
"""

import meilisearch
import yaml
import argparse
import pandas as pd


def query_meilisearch(
    query: str, index_name: str, client: meilisearch.Client, limit: int = 20
) -> dict:
    """Run a query and return full results including documents"""
    results = client.get_index(index_name).search(
        query,
        {
            "limit": limit,
            "attributesToRetrieve": ["*"],  # Get all fields for NDCG evaluation
            "showRankingScore": True,  # Include ranking scores
            "showRankingScoreDetails": True,  # Include detailed ranking info
            # "hybrid": {"embedder": "LLAMA_JINA_PROVIDER"},
        },
    )
    return results


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

    # Run queries and store results
    results = []
    for query in df["primary_search"].astype(str).str.strip():
        print(f"Running query: {query}")
        query_results = query_meilisearch(query, index_name, client, args.limit)

        # Store full results including hits (actual documents) for NDCG calculation
        result_entry = {
            "query": query,
            "related_terms": related_map.get(query, ""),
            "hits": query_results.get("hits", []),
            "processing_time_ms": query_results.get("processingTimeMs"),
            "total_hits": query_results.get("estimatedTotalHits", 0),
            "limit": query_results.get("limit"),
            "offset": query_results.get("offset"),
        }
        results.append(result_entry)

    # Save results to output file
    import json

    with open(args.output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.output_file}")
    print(f"Processed {len(results)} queries")


if __name__ == "__main__":
    main()
