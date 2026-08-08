#!/usr/bin/env python3
"""Wiki-ready infrastructure runbook for the embedding/indexing pipeline.

The pipeline is:

    Vast.ai offer -> standard vLLM image -> local Ray -> Nomic embeddings
        -> authenticated public REST endpoint -> Meilisearch REST embedder
        -> Constitutional Observer document indexing

Run ``python infra.py wiki`` for the complete Markdown runbook.
Commands which create billable infrastructure or index data are dry-run by
default and require ``--execute`` before this script will run them.

No credentials are stored in this file. Generated Meilisearch configuration is
ignored by this repository's ``*.yaml`` gitignore rule, but should still be
treated as a secret because it contains both Meilisearch and Vast API tokens.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


DEFAULT_VASTAI = "~/Library/Python/3.14/bin/vastai"
DEFAULT_IMAGE = "vastai/vllm:v0.26.0-cuda-12.9"
DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v2-moe"
DEFAULT_CONFIG = "meilisearch_config.yaml"
DEFAULT_PREFIX = "state_legislature_debates"

OFFER_QUERY = (
    "num_gpus=1 gpu_ram>=12 compute_cap>=700 cuda_vers>=12.9 "
    "disk_space>=40 direct_port_count>=5 reliability>0.98"
)


def shell_join(parts: list[str | Path]) -> str:
    """Return a copy-pasteable shell command."""
    return shlex.join(str(part) for part in parts)


def run_or_print(command: list[str | Path], execute: bool) -> int:
    """Print a command, or run it after explicit authorization."""
    print(f"$ {shell_join(command)}")
    if not execute:
        print("Dry run only; add --execute to run it.")
        return 0
    return subprocess.run([str(part) for part in command], check=False).returncode


def vast_search_command(vastai: str) -> list[str]:
    return [
        str(Path(vastai).expanduser()),
        "search",
        "offers",
        OFFER_QUERY,
        "--order",
        "dph",
        "--limit",
        "20",
    ]


def vast_environment(model: str) -> str:
    portal_config = (
        "localhost:1111:11111:/:Instance Portal|"
        "localhost:8000:18000:/docs:vLLM API|"
        "localhost:8265:28265:/:Ray Dashboard"
    )
    vllm_args = (
        "--runner pooling --download-dir /workspace/models "
        "--host 127.0.0.1 --port 18000"
    )
    ray_args = (
        "--head --port 6379 --dashboard-host 127.0.0.1 "
        "--dashboard-port 28265"
    )
    return " ".join(
        [
            "-p 1111:1111",
            "-p 8000:8000",
            "-p 8265:8265",
            "-p 8080:8080",
            "-e OPEN_BUTTON_PORT=1111",
            "-e OPEN_BUTTON_TOKEN=1",
            "-e JUPYTER_DIR=/",
            "-e DATA_DIRECTORY=/workspace/",
            f"-e PORTAL_CONFIG={shlex.quote(portal_config)}",
            f"-e VLLM_MODEL={shlex.quote(model)}",
            f"-e MODEL_NAME={shlex.quote(model)}",
            f"-e VLLM_ARGS={shlex.quote(vllm_args)}",
            "-e AUTO_PARALLEL=true",
            "-e RAY_ADDRESS=127.0.0.1:6379",
            f"-e RAY_ARGS={shlex.quote(ray_args)}",
        ]
    )


def vast_create_command(
    vastai: str,
    offer_id: str,
    image: str,
    model: str,
    disk: int,
) -> list[str]:
    return [
        str(Path(vastai).expanduser()),
        "create",
        "instance",
        offer_id,
        "--image",
        image,
        "--disk",
        str(disk),
        "--env",
        vast_environment(model),
        "--onstart-cmd",
        "entrypoint.sh",
        "--jupyter",
        "--ssh",
        "--direct",
        "--cancel-unavail",
    ]


def ssh_prefix(host: str, port: int, identity: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "ConnectTimeout=15",
        "-p",
        str(port),
        "-i",
        str(Path(identity).expanduser()),
        f"root@{host}",
    ]


def server_check_command(host: str, port: int, identity: str) -> list[str]:
    remote = dedent(
        """\
        set -e
        supervisorctl status ray vllm
        curl -fsS http://127.0.0.1:18000/health
        printf '\nhealth=ok\n'
        curl -fsS http://127.0.0.1:18000/v1/models | jq '{models:[.data[].id]}'
        curl -fsS http://127.0.0.1:18000/v1/embeddings \
          -H 'Content-Type: application/json' \
          -d '{"model":"nomic-ai/nomic-embed-text-v2-moe","input":"search_query: What is constitutional law?"}' \
          | jq '{model,dimensions:(.data[0].embedding|length),usage}'
        """
    )
    return [*ssh_prefix(host, port, identity), remote]


def meilisearch_config(
    *,
    meili_url: str,
    meili_key: str,
    vllm_base_url: str,
    vast_token: str,
    index_code: str,
    data_path: Path,
    index_name: str,
    model: str,
) -> str:
    embed_url = f"{vllm_base_url.rstrip('/')}/embeddings"
    metadata_path = data_path / "all_metadata.json"
    return dedent(
        f'''\
        connection:
          URL: {meili_url!r}
          API_KEY: {meili_key!r}

        embeddings:
          nomic_v2:
            source: rest
            dimensions: 768
            url: {embed_url!r}
            apiKey: {vast_token!r}
            request:
              model: {model!r}
              input:
                - "{{{{text}}}}"
                - "{{{{..}}}}"
              encoding_format: float
            response:
              data:
                - embedding: "{{{{embedding}}}}"
                - "{{{{..}}}}"
            documentTemplate: "search_document: {{{{doc.__discussions}}}}"

        index_config:
          global:
            batch_size: 100

          {index_code}:
            index_name: {index_name!r}
            files_path: {str(data_path)!r}
            metadata_path: {str(metadata_path)!r}
            processor: functional
            batch_size: 100
            embedding_refs:
              - nomic_v2
            chunking:
              max_chunk_len: 200
        '''
    )


def write_config(content: str, output: Path | None, force: bool) -> int:
    if output is None:
        print(content, end="")
        return 0
    if output.exists() and not force:
        print(
            f"Refusing to overwrite {output}; pass --force if intentional.",
            file=sys.stderr,
        )
        return 2
    output.write_text(content, encoding="utf-8")
    try:
        output.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote secret configuration to {output} (mode 0600).")
    return 0


def index_command(
    *,
    stage: str,
    config: Path,
    index_codes: list[str],
    canary_limit: int,
) -> list[str]:
    command: list[str | Path] = [
        "uv",
        "run",
        "python",
        "manage_collection.py",
    ]
    if stage == "create":
        command.append("create")
    else:
        command.append("upload")
    command.extend(["--config", config, "--index-codes", *index_codes])
    if stage == "canary":
        command.extend(["--limit", str(canary_limit)])
    return [str(part) for part in command]


def wiki_markdown() -> str:
    return dedent(
        f"""\
        # Infrastructure pipeline: Vast.ai to Meilisearch indexing

        ## Architecture

        `Vast.ai GPU -> Ray -> vLLM -> authenticated /v1/embeddings -> Meilisearch REST embedder -> document index`

        The standard vLLM image is required. Do not use `vllm-omni` for this
        text-embedding model. Ray must appear in `PORTAL_CONFIG`; otherwise the
        image disables Ray while vLLM waits for it and port 18000 never opens.

        ## 1. Find an offer

        ```bash
        python infra.py vast-search --execute
        ```

        ## 2. Create the instance

        ```bash
        python infra.py vast-create <OFFER_ID> --execute
        ```

        This uses `nomic-ai/nomic-embed-text-v2-moe`, CUDA 12.9, 40 GB disk,
        and exposes the token-authenticated vLLM API through Vast's Caddy edge.

        ## 3. Connect and wait for readiness

        ```bash
        ssh -p <SSH_PORT> root@<SSH_HOST> -L 8080:localhost:8080 -i ~/.ssh/aruvu

        supervisorctl status ray vllm
        tail -f /var/log/portal/vllm.log

        until curl -fsS http://127.0.0.1:18000/health; do sleep 5; done
        ```

        Initial startup downloads about 1.9 GB of model weights and builds the
        vLLM compile cache. A healthy embedding has 768 dimensions:

        ```bash
        curl -fsS http://127.0.0.1:18000/v1/embeddings \\
          -H 'Content-Type: application/json' \\
          -d '{{"model":"{DEFAULT_MODEL}","input":"search_query: What is constitutional law?"}}' \\
          | jq '{{model,dimensions:(.data[0].embedding|length),usage}}'
        ```

        ## 4. Discover the public endpoint and token

        Run these on the machine that will prepare the Meilisearch config:

        ```bash
        VAST_TOKEN=$(ssh -p <SSH_PORT> -i ~/.ssh/aruvu root@<SSH_HOST> \\
          'printf %s "$OPEN_BUTTON_TOKEN"')

        VLLM_BASE_URL=$(
          ssh -p <SSH_PORT> -i ~/.ssh/aruvu root@<SSH_HOST> \\
            'curl -fsS http://127.0.0.1:11111/capabilities/endpoints' |
          jq -r '.[] | select(.service == "vLLM API") | .base_url'
        )

        export VAST_TOKEN VLLM_BASE_URL

        export MEILI_URL="https://your-meilisearch-host"
        read -rsp "Meilisearch admin key: " MEILI_KEY
        printf '\\n'
        export MEILI_KEY
        ```

        Do not commit either token. Generate the ignored local configuration:

        ```bash
        python infra.py render-config \\
          --index-code KA \\
          --data-path /datasets/legislature_debates/KA \\
          --output meilisearch_config.yaml
        ```

        The generated REST embedder sends batched OpenAI-compatible requests,
        extracts `data[].embedding`, and prefixes indexed text with
        `search_document: `. Nomic queries must use `search_query: `.

        ## 5. Validate source data

        ```bash
        test -f /datasets/legislature_debates/KA/all_metadata.json
        test -d /datasets/legislature_debates/KA/downloads
        wc -l /datasets/legislature_debates/KA/all_metadata.json
        ```

        ## 6. Install project dependencies and index

        ```bash
        uv sync

        # Create/update the index and embedder settings
        python infra.py index --stage create --index-codes KA --execute

        # Canary upload
        python infra.py index --stage canary --index-codes KA --limit 10 --execute

        # Full upload after checking Meilisearch tasks/errors
        python infra.py index --stage full --index-codes KA --execute
        ```

        The project writes `meilisearch_upload_<CODE>.json` and
        `metadata_errors_<CODE>.json` diagnostic files. Keep the Vast instance
        running until Meilisearch has completed all queued embedding tasks.

        ## 7. Check Meilisearch completion

        ```bash
        curl -fsS "$MEILI_URL/tasks?statuses=enqueued,processing&limit=1" \\
          -H "Authorization: Bearer $MEILI_KEY" | jq .

        curl -fsS "$MEILI_URL/tasks?statuses=failed&limit=20" \\
          -H "Authorization: Bearer $MEILI_KEY" | jq .

        curl -fsS "$MEILI_URL/indexes/state_legislature_debates_ka/stats" \\
          -H "Authorization: Bearer $MEILI_KEY" | jq .
        ```

        ## Persistence

        Vast stop/start preserves the container and downloaded model. Recycling
        or destroying it removes changes unless `/workspace` is backed by a
        persistent Vast volume. Recreate with the command above after recycling.

        ## References

        - [Vast vLLM image tags](https://hub.docker.com/r/vastai/vllm/tags)
        - [Nomic Embed v2 model card](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)
        - [Meilisearch REST embedder configuration](https://www.meilisearch.com/docs/capabilities/hybrid_search/how_to/configure_rest_embedder)
        """
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Document and operate the Vast -> vLLM -> Meilisearch pipeline."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    wiki = subparsers.add_parser("wiki", help="Print the complete Markdown runbook.")
    wiki.set_defaults(handler=handle_wiki)

    search = subparsers.add_parser("vast-search", help="Find compatible Vast offers.")
    search.add_argument("--vastai", default=DEFAULT_VASTAI)
    search.add_argument("--execute", action="store_true")
    search.set_defaults(handler=handle_vast_search)

    create = subparsers.add_parser("vast-create", help="Create a Vast instance.")
    create.add_argument("offer_id")
    create.add_argument("--vastai", default=DEFAULT_VASTAI)
    create.add_argument("--image", default=DEFAULT_IMAGE)
    create.add_argument("--model", default=DEFAULT_MODEL)
    create.add_argument("--disk", type=int, default=40)
    create.add_argument("--execute", action="store_true")
    create.set_defaults(handler=handle_vast_create)

    check = subparsers.add_parser("server-check", help="Check Ray, vLLM, and embeddings.")
    check.add_argument("--host", required=True)
    check.add_argument("--port", type=int, required=True)
    check.add_argument("--identity", default="~/.ssh/aruvu")
    check.add_argument("--execute", action="store_true")
    check.set_defaults(handler=handle_server_check)

    render = subparsers.add_parser(
        "render-config", help="Render a secret local Meilisearch YAML configuration."
    )
    render.add_argument("--meili-url", help="Defaults to MEILI_URL.")
    render.add_argument("--meili-key", help="Defaults to MEILI_KEY.")
    render.add_argument("--vllm-base-url", help="Defaults to VLLM_BASE_URL.")
    render.add_argument("--vast-token", help="Defaults to VAST_TOKEN.")
    render.add_argument("--index-code", required=True)
    render.add_argument("--data-path", type=Path, required=True)
    render.add_argument("--index-name")
    render.add_argument("--model", default=DEFAULT_MODEL)
    render.add_argument("--output", type=Path)
    render.add_argument("--force", action="store_true")
    render.set_defaults(handler=handle_render_config)

    index = subparsers.add_parser("index", help="Create or populate Meilisearch indexes.")
    index.add_argument("--stage", choices=("create", "canary", "full"), required=True)
    index.add_argument("--config", type=Path, default=Path(DEFAULT_CONFIG))
    index.add_argument("--index-codes", nargs="+", required=True)
    index.add_argument("--limit", type=int, default=10)
    index.add_argument("--execute", action="store_true")
    index.set_defaults(handler=handle_index)

    return parser


def handle_wiki(_args: argparse.Namespace) -> int:
    print(wiki_markdown(), end="")
    return 0


def handle_vast_search(args: argparse.Namespace) -> int:
    return run_or_print(vast_search_command(args.vastai), args.execute)


def handle_vast_create(args: argparse.Namespace) -> int:
    command = vast_create_command(
        args.vastai,
        args.offer_id,
        args.image,
        args.model,
        args.disk,
    )
    return run_or_print(command, args.execute)


def handle_server_check(args: argparse.Namespace) -> int:
    command = server_check_command(args.host, args.port, args.identity)
    return run_or_print(command, args.execute)


def handle_render_config(args: argparse.Namespace) -> int:
    secret_inputs = {
        "meili_url": (args.meili_url, "MEILI_URL"),
        "meili_key": (args.meili_key, "MEILI_KEY"),
        "vllm_base_url": (args.vllm_base_url, "VLLM_BASE_URL"),
        "vast_token": (args.vast_token, "VAST_TOKEN"),
    }
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name, (argument, environment_name) in secret_inputs.items():
        value = argument or os.environ.get(environment_name)
        if value:
            resolved[name] = value
        else:
            missing.append(f"--{name.replace('_', '-')} or {environment_name}")
    if missing:
        print("Missing required values: " + ", ".join(missing), file=sys.stderr)
        return 2

    index_code = args.index_code.upper()
    index_name = args.index_name or f"{DEFAULT_PREFIX}_{index_code.lower()}"
    content = meilisearch_config(
        meili_url=resolved["meili_url"],
        meili_key=resolved["meili_key"],
        vllm_base_url=resolved["vllm_base_url"],
        vast_token=resolved["vast_token"],
        index_code=index_code,
        data_path=args.data_path.expanduser().resolve(),
        index_name=index_name,
        model=args.model,
    )
    return write_config(content, args.output, args.force)


def handle_index(args: argparse.Namespace) -> int:
    if not Path("manage_collection.py").exists():
        print("Run this command from the upload-scripts repository root.", file=sys.stderr)
        return 2
    command = index_command(
        stage=args.stage,
        config=args.config,
        index_codes=[code.upper() for code in args.index_codes],
        canary_limit=args.limit,
    )
    return run_or_print(command, args.execute)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
