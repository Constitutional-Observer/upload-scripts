"""
Script to run a sequence of queries on an index, and store the results

The results can then be used for comparison
"""

import meilisearch
import yaml
import argparse


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
        },
    )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("meilisearch_config")
    parser.add_argument("queries_file", help="File containing queries, one per line")
    parser.add_argument("index_name", help="Name of the index to query")
    parser.add_argument(
        "output_file", help="File to store query results in JSON format"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of results per query (default: 20)",
    )
    args = parser.parse_args()

    with open(args.meilisearch_config) as f:
        config = yaml.safe_load(f)

    client = meilisearch.Client(
        config["connection"]["URL"], config["connection"]["API_KEY"]
    )
    client.health()

    # Read queries from file
    with open(args.queries_file) as f:
        queries = [line.strip() for line in f if line.strip()]

    # Run queries and store results
    results = {}
    for query in queries:
        print(f"Running query: {query}")
        query_results = query_meilisearch(query, args.index_name, client, args.limit)

        # Store full results including hits (actual documents) for NDCG calculation
        results[query] = {
            "query": query,
            "hits": query_results.get("hits", []),  # Actual retrieved documents
            "processing_time_ms": query_results.get("processingTimeMs"),
            "total_hits": query_results.get("estimatedTotalHits", 0),
            "limit": query_results.get("limit"),
            "offset": query_results.get("offset"),
        }

    # Save results to output file
    import json

    with open(args.output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to {args.output_file}")
    print(f"Processed {len(queries)} queries")


if __name__ == "__main__":
    main()
