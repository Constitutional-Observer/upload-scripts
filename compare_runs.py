"""
Streamlit UI for viewing and comparing query results from run_queries.py

Usage: streamlit run compare_runs.py
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import numpy as np
import json


def dcg_at_k(relevance_scores, k):
    """
    Calculate Discounted Cumulative Gain at rank k.

    Args:
        relevance_scores: List of relevance scores (higher = more relevant)
        k: Cutoff rank

    Returns:
        DCG@k score
    """
    relevance_scores = relevance_scores[:k]
    dcg = 0.0
    for i, rel in enumerate(relevance_scores):
        dcg += (2**rel - 1) / np.log2(i + 2)
    return dcg


def ndcg_at_k(gold_scores, system_scores, k):
    """
    Calculate Normalized Discounted Cumulative Gain at rank k.

    Args:
        gold_scores: List of relevance scores in gold standard order (descending)
        system_scores: List of relevance scores in system ranking order
        k: Cutoff rank

    Returns:
        NDCG@k score (0.0 to 1.0)
    """
    # Sort gold scores in descending order for ideal DCG
    gold_scores_sorted = sorted(gold_scores, reverse=True)

    # Calculate DCG for system
    dcg = dcg_at_k(system_scores, k)

    # Calculate ideal DCG
    idcg = dcg_at_k(gold_scores_sorted, k)

    if idcg == 0:
        return 0.0
    return dcg / idcg


def get_ndcg_for_query(hits1, hits2, k):
    """
    Calculate NDCG@k for a single query, using hits1 as gold standard and hits2 as system.

    Args:
        hits1: List of hit dicts from baseline (first) run
        hits2: List of hit dicts from second run
        k: Cutoff rank

    Returns:
        NDCG@k score
    """
    if not hits1 or not hits2:
        return 0.0

    # Build gold standard: map doc_id to relevance score from first run
    # Use rankingScore if available, otherwise use position-based relevance
    gold_relevance = {}
    for idx, hit in enumerate(hits1):
        doc_id = hit.get("id")
        if doc_id:
            rel_score = hit.get("rankingScore", len(hits1) - idx)
            gold_relevance[doc_id] = float(rel_score)

    if not gold_relevance:
        return 0.0

    # Get gold scores sorted by relevance (descending) for IDCG
    gold_docs_sorted = sorted(
        gold_relevance.keys(), key=lambda x: gold_relevance[x], reverse=True
    )
    gold_scores = [gold_relevance[doc] for doc in gold_docs_sorted]

    # Build system scores: for each position in hits2 (up to k),
    # get the relevance from gold standard (0 if document not in gold standard)
    # This properly captures the position of relevant documents in the system ranking
    system_scores = []
    for hit in hits2[:k]:  # Only look at top k results
        doc_id = hit.get("id")
        if doc_id and doc_id in gold_relevance:
            system_scores.append(gold_relevance[doc_id])
        else:
            system_scores.append(0.0)

    # Pad with zeros if we have fewer than k results
    while len(system_scores) < k:
        system_scores.append(0.0)

    # Pad gold scores to k as well
    while len(gold_scores) < k:
        gold_scores.append(0.0)

    return ndcg_at_k(gold_scores[:k], system_scores[:k], k)


def calculate_ndcg_metrics(df1, df2, k_values=[1, 3, 5, 10]):
    """
    Calculate NDCG metrics across all common queries.

    Args:
        df1: First dataframe (baseline/gold standard)
        df2: Second dataframe (system to evaluate)
        k_values: List of k values to compute NDCG@k for

    Returns:
        Tuple of (per_query_ndcg, overall_ndcg)
        per_query_ndcg: Dict mapping query to dict of {k: ndcg_score}
        overall_ndcg: Dict mapping k to average NDCG@k across all queries
    """
    # Find common queries
    queries1 = set(df1["query"].unique())
    queries2 = set(df2["query"].unique())
    common_queries = queries1 & queries2

    per_query_ndcg = {}
    overall_ndcg = {k: [] for k in k_values}

    for query in common_queries:
        row1 = df1[df1["query"] == query].iloc[0]
        row2 = df2[df2["query"] == query].iloc[0]

        hits1 = parse_hits_for_display(row1.get("hits"))
        hits2 = parse_hits_for_display(row2.get("hits"))

        if not hits1 or not hits2:
            continue

        query_ndcg = {}
        for k in k_values:
            ndcg = get_ndcg_for_query(hits1, hits2, k)
            query_ndcg[f"NDCG@{k}"] = ndcg
            overall_ndcg[k].append(ndcg)

        per_query_ndcg[query] = query_ndcg

    # Calculate averages
    overall_ndcg_avg = {}
    for k in k_values:
        if overall_ndcg[k]:
            overall_ndcg_avg[f"NDCG@{k}"] = np.mean(overall_ndcg[k])
        else:
            overall_ndcg_avg[f"NDCG@{k}"] = 0.0

    return per_query_ndcg, overall_ndcg_avg


def load_results(file_path):
    """Load results from parquet file"""
    file_path = Path(file_path)

    if file_path.suffix == ".parquet":
        df = pd.read_parquet(file_path)
        return df
    else:
        st.error(
            f"Unsupported file format: {file_path.suffix}. Please use parquet files."
        )
        return None


def parse_hits_for_display(hits_raw):
    """Parse hits data from various formats into a list of dictionaries"""
    if hits_raw is pd.NaT:
        return None

    # Convert pandas objects or custom types
    if hasattr(hits_raw, "to_dict"):
        hits_raw = hits_raw.to_dict()
    elif hasattr(hits_raw, "__dict__"):
        hits_raw = vars(hits_raw)

    # Try to parse as JSON string
    if isinstance(hits_raw, str):
        try:
            return json.loads(hits_raw)
        except json.JSONDecodeError, TypeError:
            return None
    elif isinstance(hits_raw, list):
        return hits_raw

    return None


def load_metadata(file_path):
    """Load metadata from sidecar JSON file"""
    metadata_path = Path(file_path) if isinstance(file_path, str) else file_path
    metadata_file = metadata_path.with_suffix(metadata_path.suffix + ".metadata.json")

    # Also try replacing .parquet with .metadata.json
    if not metadata_file.exists():
        if str(metadata_file).endswith(".parquet.metadata.json"):
            metadata_file = metadata_path.parent / (
                metadata_path.stem + ".metadata.json"
            )

    if metadata_file.exists():
        try:
            with open(metadata_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError, IOError:
            pass
    return None


def parse_metadata(metadata_json):
    """Parse metadata from JSON string (for backwards compatibility)"""
    if metadata_json is None or pd.isna(metadata_json):
        return {}
    try:
        if isinstance(metadata_json, str):
            return json.loads(metadata_json)
        elif isinstance(metadata_json, dict):
            return metadata_json
        else:
            return {}
    except json.JSONDecodeError, TypeError:
        return {}


def compare_dataframes(df1, df2, df1_name, df2_name, file1_path=None, file2_path=None):
    """Compare two result dataframes and return comparison metrics"""

    # Basic stats
    stats1 = {
        "Total queries": len(df1),
        "Avg hits per query": df1["total_hits"].mean()
        if "total_hits" in df1.columns
        else 0,
        "Avg processing time (ms)": df1["processing_time_ms"].mean()
        if "processing_time_ms" in df1.columns
        else 0,
        "Total documents retrieved": df1["total_hits"].sum()
        if "total_hits" in df1.columns
        else 0,
    }

    stats2 = {
        "Total queries": len(df2),
        "Avg hits per query": df2["total_hits"].mean()
        if "total_hits" in df2.columns
        else 0,
        "Avg processing time (ms)": df2["processing_time_ms"].mean()
        if "processing_time_ms" in df2.columns
        else 0,
        "Total documents retrieved": df2["total_hits"].sum()
        if "total_hits" in df2.columns
        else 0,
    }

    # Find common queries
    queries1 = set(df1["query"].unique())
    queries2 = set(df2["query"].unique())

    common_queries = queries1 & queries2
    only_in_1 = queries1 - queries2
    only_in_2 = queries2 - queries1

    comparison = {
        "Common queries": len(common_queries),
        "Only in " + df1_name: len(only_in_1),
        "Only in " + df2_name: len(only_in_2),
    }

    # Extract metadata for comparison context
    metadata1 = {}
    metadata2 = {}
    index_metadata1 = {}
    index_metadata2 = {}

    # Try loading from sidecar files first
    if file1_path:
        file_metadata = load_metadata(file1_path)
        if file_metadata:
            metadata1 = file_metadata.get("query_run_metadata", {})
            index_metadata1 = file_metadata.get("index_metadata", {})
    # Fallback to legacy columns in dataframe
    if not metadata1 and "query_run_metadata" in df1.columns and len(df1) > 0:
        metadata1 = parse_metadata(df1.iloc[0].get("query_run_metadata"))
    if not index_metadata1 and "index_metadata" in df1.columns and len(df1) > 0:
        index_metadata1 = parse_metadata(df1.iloc[0].get("index_metadata"))

    if file2_path:
        file_metadata = load_metadata(file2_path)
        if file_metadata:
            metadata2 = file_metadata.get("query_run_metadata", {})
            index_metadata2 = file_metadata.get("index_metadata", {})
    # Fallback to legacy columns in dataframe
    if not metadata2 and "query_run_metadata" in df2.columns and len(df2) > 0:
        metadata2 = parse_metadata(df2.iloc[0].get("query_run_metadata"))
    if not index_metadata2 and "index_metadata" in df2.columns and len(df2) > 0:
        index_metadata2 = parse_metadata(df2.iloc[0].get("index_metadata"))

    # Calculate NDCG metrics (df1 is baseline/gold standard, df2 is system)
    k_values = [1, 3, 5, 10]
    per_query_ndcg, overall_ndcg = calculate_ndcg_metrics(df1, df2, k_values)

    return (
        stats1,
        stats2,
        comparison,
        per_query_ndcg,
        overall_ndcg,
        metadata1,
        metadata2,
        index_metadata1,
        index_metadata2,
    )


def main():
    st.set_page_config(page_title="Query Results Comparator", layout="wide")

    st.title("🔍 Query Results Viewer & Comparator")
    st.markdown("""
    This tool allows you to view the output from `run_queries.py` (parquet files) and compare 
    results between different runs.
    """)

    # Sidebar for file selection
    st.sidebar.header("File Selection")

    # Configurable source directory
    st.sidebar.markdown("**Source Directory**")
    source_dir = st.sidebar.text_input(
        "Directory containing result files",
        value="benchmark_runs",
        key="source_dir",
        help="Enter the directory path where result files are stored",
    )

    # Available files
    result_files = []

    # Look for result files in the source directory
    source_path = Path(source_dir)
    if source_path.exists() and source_path.is_dir():
        result_files.extend(source_path.glob("*result*.parquet"))
        result_files.extend(source_path.glob("*results.parquet"))
    else:
        st.sidebar.warning(
            f"Directory '{source_dir}' not found. Falling back to current directory."
        )
        result_files.extend(Path(".").glob("*result*.parquet"))
        result_files.extend(Path(".").glob("*results.parquet"))

    # Remove duplicates
    result_files = list(set(result_files))

    # Sort by modification time (newest first)
    result_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # File selection
    st.sidebar.markdown("**Select files to compare**")

    # Keep full paths but display only filenames
    available_files = [str(f) for f in result_files if f.exists()]

    def format_filename(path):
        """Extract just the filename for display"""
        return Path(path).name

    # Also allow manual file path entry
    col1, col2 = st.sidebar.columns(2)

    with col1:
        file1_option = st.selectbox(
            "First file",
            options=available_files,
            format_func=format_filename,
            key="file1_select",
        )

    with col2:
        file2_option = st.selectbox(
            "Second file (optional)",
            options=["None"] + available_files,
            format_func=lambda x: format_filename(x) if x != "None" else "None",
            key="file2_select",
        )

    # Or allow custom file paths
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Or enter custom file paths**")

    custom_file1 = st.sidebar.text_input(
        "First file path", value="", key="custom_file1"
    )
    custom_file2 = st.sidebar.text_input(
        "Second file path (optional)", value="", key="custom_file2"
    )

    # Determine which files to use
    if custom_file1:
        file1_path = custom_file1
    else:
        file1_path = file1_option if file1_option else None

    if custom_file2:
        file2_path = custom_file2
    else:
        file2_path = file2_option if file2_option and file2_option != "None" else None

    # Load data
    df1 = None
    df2 = None

    if file1_path:
        try:
            df1 = load_results(file1_path)
        except Exception as e:
            st.error(f"Error loading {file1_path}: {e}")

    if file2_path:
        try:
            df2 = load_results(file2_path)
        except Exception as e:
            st.error(f"Error loading {file2_path}: {e}")

    # Display based on what's loaded
    if df1 is None and df2 is None:
        st.warning("Please select at least one file to view.")
        return

    # Tabs for different views
    tab_settings, tab_compare = st.tabs(["Settings", "Compare Results"])

    with tab_settings:
        st.header("Settings")

        # Handle both single and dual file scenarios
        if df1 is not None and df2 is not None:
            # Two files: show comparison/differences
            df1_name = Path(file1_path).name
            df2_name = Path(file2_path).name

            (
                stats1,
                stats2,
                comparison,
                per_query_ndcg,
                overall_ndcg,
                metadata1,
                metadata2,
                index_metadata1,
                index_metadata2,
            ) = compare_dataframes(df1, df2, df1_name, df2_name, file1_path, file2_path)

            # Comparison overview
            st.subheader("Comparison Overview")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(f"**{df1_name}**")
                for key, value in stats1.items():
                    if isinstance(value, float):
                        st.metric(key, f"{value:.2f}")
                    else:
                        st.metric(key, value)

            with col2:
                st.markdown(f"**{df2_name}**")
                for key, value in stats2.items():
                    if isinstance(value, float):
                        st.metric(key, f"{value:.2f}")
                    else:
                        st.metric(key, value)

            with col3:
                st.markdown("**Query Overlap**")
                for key, value in comparison.items():
                    st.metric(key, value)

            # Show query run metadata comparison
            if metadata1 or metadata2:
                st.markdown("---")
                st.subheader("Query Run Metadata Comparison")

                col1, col2 = st.columns(2)

                with col1:
                    if metadata1:
                        st.markdown(f"**{df1_name}**")
                        for key, value in metadata1.items():
                            st.text(f"{key}: {value}")
                    else:
                        st.info("No query run metadata available")

                with col2:
                    if metadata2:
                        st.markdown(f"**{df2_name}**")
                        for key, value in metadata2.items():
                            st.text(f"{key}: {value}")
                    else:
                        st.info("No query run metadata available")

            # Show index settings comparison
            if index_metadata1 or index_metadata2:
                st.markdown("---")
                st.subheader("Index Settings Comparison")

                # Display key settings side by side
                col1, col2 = st.columns(2)

                with col1:
                    if index_metadata1:
                        st.markdown(f"**{df1_name}**")
                        settings1 = index_metadata1.get("settings", {})
                        if settings1:
                            st.text(
                                f"Ranking rules: {', '.join(settings1.get('ranking_rules', []))}"
                            )
                            st.text(
                                f"Searchable attributes: {len(settings1.get('searchable_attributes', []))}"
                            )
                            st.text(
                                f"Filterable attributes: {len(settings1.get('filterable_attributes', []))}"
                            )

                        stats1_info = index_metadata1.get("stats", {})
                        if stats1_info:
                            st.text(
                                f"Documents in index: {stats1_info.get('number_of_documents', 'N/A')}"
                            )

                        embedders1 = index_metadata1.get("embedders", {})
                        if embedders1:
                            st.text(
                                f"Embedders configured: {list(embedders1.keys()) if isinstance(embedders1, dict) else 'N/A'}"
                            )
                    else:
                        st.info("No index metadata available")

                with col2:
                    if index_metadata2:
                        st.markdown(f"**{df2_name}**")
                        settings2 = index_metadata2.get("settings", {})
                        if settings2:
                            st.text(
                                f"Ranking rules: {', '.join(settings2.get('ranking_rules', []))}"
                            )
                            st.text(
                                f"Searchable attributes: {len(settings2.get('searchable_attributes', []))}"
                            )
                            st.text(
                                f"Filterable attributes: {len(settings2.get('filterable_attributes', []))}"
                            )

                        stats2_info = index_metadata2.get("stats", {})
                        if stats2_info:
                            st.text(
                                f"Documents in index: {stats2_info.get('number_of_documents', 'N/A')}"
                            )

                        embedders2 = index_metadata2.get("embedders", {})
                        if embedders2:
                            st.text(
                                f"Embedders configured: {list(embedders2.keys()) if isinstance(embedders2, dict) else 'N/A'}"
                            )
                    else:
                        st.info("No index metadata available")

                # Show detailed index settings in expander
                with st.expander("View full index settings JSON"):
                    col1, col2 = st.columns(2)
                    with col1:
                        if index_metadata1:
                            st.json(index_metadata1)
                        else:
                            st.text("No metadata available")
                    with col2:
                        if index_metadata2:
                            st.json(index_metadata2)
                        else:
                            st.text("No metadata available")

        elif df1 is not None:
            # Single file: show its metadata and index settings
            st.subheader(f"File: {file1_path}")

            # Display query run metadata if available
            run_metadata = {}
            index_metadata = {}
            file_metadata = load_metadata(file1_path) if file1_path else None
            if file_metadata:
                run_metadata = file_metadata.get("query_run_metadata", {})
                index_metadata = file_metadata.get("index_metadata", {})
            elif "query_run_metadata" in df1.columns and len(df1) > 0:
                run_metadata = parse_metadata(df1.iloc[0].get("query_run_metadata"))
            if "index_metadata" in df1.columns and len(df1) > 0 and not index_metadata:
                index_metadata = parse_metadata(df1.iloc[0].get("index_metadata"))

            if run_metadata:
                st.markdown("---")
                st.subheader("Query Run Metadata")
                metadata_cols = st.columns(3)
                with metadata_cols[0]:
                    st.text(f"Timestamp: {run_metadata.get('timestamp', 'N/A')}")
                with metadata_cols[1]:
                    hybrid_enabled = run_metadata.get("hybrid_search_enabled", False)
                    st.text(f"Hybrid search: {'Yes' if hybrid_enabled else 'No'}")
                with metadata_cols[2]:
                    st.text(f"Limit: {run_metadata.get('limit', 'N/A')}")

            # Display index metadata if available
            if index_metadata:
                st.markdown("---")
                st.subheader("Index Settings at Query Time")

                settings = index_metadata.get("settings", {})
                if settings:
                    meta_cols = st.columns(3)
                    with meta_cols[0]:
                        ranking_rules = settings.get("ranking_rules", [])
                        st.text(
                            f"Ranking rules: {', '.join(ranking_rules) if ranking_rules else 'N/A'}"
                        )
                    with meta_cols[1]:
                        st.text(
                            f"Searchable attrs: {len(settings.get('searchable_attributes', []))}"
                        )
                    with meta_cols[2]:
                        st.text(
                            f"Filterable attrs: {len(settings.get('filterable_attributes', []))}"
                        )

                stats_info = index_metadata.get("stats", {})
                if stats_info:
                    st.text(
                        f"Documents in index: {stats_info.get('number_of_documents', 'N/A')}"
                    )

                embedders = index_metadata.get("embedders", {})
                if embedders:
                    if isinstance(embedders, dict):
                        st.text(f"Embedders: {', '.join(embedders.keys())}")

                # Show full JSON
                with st.expander("View full index settings JSON"):
                    st.json(index_metadata)

        elif df2 is not None:
            # Single file (df2 only): show its metadata and index settings
            st.subheader(f"File: {file2_path}")

            # Display query run metadata if available
            run_metadata2 = {}
            index_metadata2 = {}
            file_metadata2 = load_metadata(file2_path) if file2_path else None
            if file_metadata2:
                run_metadata2 = file_metadata2.get("query_run_metadata", {})
                index_metadata2 = file_metadata2.get("index_metadata", {})
            elif "query_run_metadata" in df2.columns and len(df2) > 0:
                run_metadata2 = parse_metadata(df2.iloc[0].get("query_run_metadata"))
            if "index_metadata" in df2.columns and len(df2) > 0 and not index_metadata2:
                index_metadata2 = parse_metadata(df2.iloc[0].get("index_metadata"))

            if run_metadata2:
                st.markdown("---")
                st.subheader("Query Run Metadata")
                metadata_cols = st.columns(3)
                with metadata_cols[0]:
                    st.text(f"Timestamp: {run_metadata2.get('timestamp', 'N/A')}")
                with metadata_cols[1]:
                    hybrid_enabled = run_metadata2.get("hybrid_search_enabled", False)
                    st.text(f"Hybrid search: {'Yes' if hybrid_enabled else 'No'}")
                with metadata_cols[2]:
                    st.text(f"Limit: {run_metadata2.get('limit', 'N/A')}")

            # Display index metadata if available
            if index_metadata2:
                st.markdown("---")
                st.subheader("Index Settings at Query Time")

                settings = index_metadata2.get("settings", {})
                if settings:
                    meta_cols = st.columns(3)
                    with meta_cols[0]:
                        ranking_rules = settings.get("ranking_rules", [])
                        st.text(
                            f"Ranking rules: {', '.join(ranking_rules) if ranking_rules else 'N/A'}"
                        )
                    with meta_cols[1]:
                        st.text(
                            f"Searchable attrs: {len(settings.get('searchable_attributes', []))}"
                        )
                    with meta_cols[2]:
                        st.text(
                            f"Filterable attrs: {len(settings.get('filterable_attributes', []))}"
                        )

                stats_info = index_metadata2.get("stats", {})
                if stats_info:
                    st.text(
                        f"Documents in index: {stats_info.get('number_of_documents', 'N/A')}"
                    )

                embedders = index_metadata2.get("embedders", {})
                if embedders:
                    if isinstance(embedders, dict):
                        st.text(f"Embedders: {', '.join(embedders.keys())}")

                # Show full JSON
                with st.expander("View full index settings JSON"):
                    st.json(index_metadata2)

    with tab_compare:
        st.header("Compare Results")

        if df1 is None or df2 is None:
            st.warning("Please load two files to compare.")
        else:
            df1_name = Path(file1_path).name
            df2_name = Path(file2_path).name

            (
                stats1,
                stats2,
                comparison,
                per_query_ndcg,
                overall_ndcg,
                metadata1,
                metadata2,
                index_metadata1,
                index_metadata2,
            ) = compare_dataframes(df1, df2, df1_name, df2_name, file1_path, file2_path)

            # Overall NDCG metrics
            if overall_ndcg:
                st.subheader("NDCG Scores (Baseline vs System)")
                st.markdown("""
                NDCG compares the second run (system) against the first run (baseline/gold standard).
                For each query, the baseline's rankingScore values are used as relevance judgments.
                """)
                st.markdown("**Overall NDCG (averaged across all common queries)**")
                ndcg_cols = st.columns(len(overall_ndcg))
                for idx, (k, score) in enumerate(overall_ndcg.items()):
                    with ndcg_cols[idx]:
                        st.metric(k, f"{score:.4f}")
                st.markdown("---")

            # Column selection for hits display
            # Get all possible columns from hits in both dataframes
            all_hit_columns = set()
            if len(df1) > 0 and "hits" in df1.columns:
                first_hits = df1.iloc[0].get("hits", None)
                if first_hits is not None and first_hits is not pd.NaT:
                    hits_list = parse_hits_for_display(first_hits)
                    if hits_list and isinstance(hits_list, list) and len(hits_list) > 0:
                        all_hit_columns.update(hits_list[0].keys())
            if len(df2) > 0 and "hits" in df2.columns:
                first_hits = df2.iloc[0].get("hits", None)
                if first_hits is not None and first_hits is not pd.NaT:
                    hits_list = parse_hits_for_display(first_hits)
                    if hits_list and isinstance(hits_list, list) and len(hits_list) > 0:
                        all_hit_columns.update(hits_list[0].keys())

            # Default to showing only __discussions
            available_hit_columns = sorted(list(all_hit_columns))
            default_hit_columns = (
                ["__discussions"]
                if "__discussions" in available_hit_columns
                else (available_hit_columns[:1] if available_hit_columns else [])
            )

            show_hit_columns = st.multiselect(
                "Select columns to display in hits",
                options=available_hit_columns,
                default=default_hit_columns,
                key="comparison_hit_cols",
            )

            # Ensure at least one column is selected
            if not show_hit_columns and available_hit_columns:
                show_hit_columns = default_hit_columns

            # Query-by-query side-by-side comparison
            queries1 = set(df1["query"].unique())
            queries2 = set(df2["query"].unique())
            all_queries = sorted(queries1 | queries2)

            st.subheader(f"Query Results Comparison ({len(all_queries)} queries)")

            # Always show all queries with no filtering
            queries_to_show = all_queries

            if not queries_to_show:
                st.warning("No queries to display.")

            for query in queries_to_show:
                st.markdown("---")
                st.markdown(f"**Query:** {query}")

                row1 = (
                    df1[df1["query"] == query].iloc[0]
                    if len(df1[df1["query"] == query]) > 0
                    else None
                )
                row2 = (
                    df2[df2["query"] == query].iloc[0]
                    if len(df2[df2["query"] == query]) > 0
                    else None
                )

                # Display NDCG scores for this query if available
                if query in per_query_ndcg:
                    ndcg_scores = per_query_ndcg[query]
                    st.markdown(
                        "**NDCG Scores:** "
                        + ", ".join([f"{k}: {v:.4f}" for k, v in ndcg_scores.items()])
                    )

                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown(f"**{df1_name}**")
                    if row1 is not None:
                        # Display individual hits as rows
                        hits_data1 = row1.get("hits", None)
                        if hits_data1 is not None and hits_data1 is not pd.NaT:
                            hits_list1 = parse_hits_for_display(hits_data1)
                            if (
                                hits_list1
                                and isinstance(hits_list1, list)
                                and len(hits_list1) > 0
                            ):
                                df_hits1 = pd.DataFrame(hits_list1)
                                # Filter to show only selected columns
                                if show_hit_columns:
                                    display_cols = [
                                        c
                                        for c in show_hit_columns
                                        if c in df_hits1.columns
                                    ]
                                    df_hits1 = df_hits1[display_cols]
                                # Reorder columns
                                column_order = []
                                for col in ["id", "rankingScore"]:
                                    if col in df_hits1.columns:
                                        column_order.append(col)
                                        df_hits1[col] = df_hits1[col].apply(
                                            lambda x: (
                                                f"{x:.4f}"
                                                if isinstance(x, (int, float))
                                                else x
                                            )
                                        )
                                for col in df_hits1.columns:
                                    if col not in column_order:
                                        column_order.append(col)
                                df_hits1 = df_hits1[column_order]
                                st.dataframe(
                                    df_hits1, use_container_width=True, height=200
                                )
                            else:
                                st.caption("No hit details available")
                    else:
                        st.info("Query not in first file")

                with col_b:
                    st.markdown(f"**{df2_name}**")
                    if row2 is not None:
                        # Display individual hits as rows
                        hits_data2 = row2.get("hits", None)
                        if hits_data2 is not None and hits_data2 is not pd.NaT:
                            hits_list2 = parse_hits_for_display(hits_data2)
                            if (
                                hits_list2
                                and isinstance(hits_list2, list)
                                and len(hits_list2) > 0
                            ):
                                df_hits2 = pd.DataFrame(hits_list2)
                                # Filter to show only selected columns
                                if show_hit_columns:
                                    display_cols = [
                                        c
                                        for c in show_hit_columns
                                        if c in df_hits2.columns
                                    ]
                                    df_hits2 = df_hits2[display_cols]
                                # Reorder columns
                                column_order = []
                                for col in ["id", "rankingScore"]:
                                    if col in df_hits2.columns:
                                        column_order.append(col)
                                        df_hits2[col] = df_hits2[col].apply(
                                            lambda x: (
                                                f"{x:.4f}"
                                                if isinstance(x, (int, float))
                                                else x
                                            )
                                        )
                                for col in df_hits2.columns:
                                    if col not in column_order:
                                        column_order.append(col)
                                df_hits2 = df_hits2[column_order]
                                st.dataframe(
                                    df_hits2, use_container_width=True, height=200
                                )
                            else:
                                st.caption("No hit details available")
                    else:
                        st.info("Query not in second file")


if __name__ == "__main__":
    main()
