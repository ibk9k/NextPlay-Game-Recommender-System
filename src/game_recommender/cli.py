"""Local serving and offline data/model commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main(argv=None):
    parser = argparse.ArgumentParser(prog="game-rs")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the local app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    prepare = commands.add_parser("prepare", help="Stream and sample the Kaggle files")
    prepare.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    prepare.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    prepare.add_argument("--users", type=int, default=2000)
    prepare.add_argument("--min-reviews", type=int, default=5)
    prepare.add_argument("--seed", type=int, default=42)
    prepare.add_argument("--max-interactions", type=int, default=2_000_000)
    neural = commands.add_parser("build-neural", help="Build pretrained description embeddings")
    neural.add_argument("--data-dir", type=Path)
    neural.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    neural.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    neural.add_argument("--batch-size", type=int, default=32)
    evaluation = commands.add_parser("evaluate", help="Run a leakage-free positive-item holdout")
    evaluation.add_argument("--data-dir", type=Path)
    evaluation.add_argument("--output", type=Path, default=Path("artifacts/evaluation.json"))
    evaluation.add_argument("--seed", type=int, default=42)
    evaluation.add_argument("--k", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "game_recommender.api:app", host=args.host, port=args.port, reload=args.reload
            )
        elif args.command == "prepare":
            from game_recommender.importer import prepare_dataset

            report = prepare_dataset(
                args.raw_dir,
                args.output_dir,
                users=args.users,
                min_reviews=args.min_reviews,
                seed=args.seed,
                max_interactions=args.max_interactions,
            )
            print(json.dumps(report, indent=2))
        else:
            from game_recommender.api import default_catalog_dir
            from game_recommender.catalog import load_catalog

            catalog = load_catalog(args.data_dir or default_catalog_dir())
            if args.command == "build-neural":
                from game_recommender.neural import build_index

                if args.batch_size < 1:
                    parser.error("--batch-size must be positive")
                report = build_index(catalog, args.output_dir, args.model, args.batch_size)
            else:
                from game_recommender.evaluation import evaluate

                report = evaluate(catalog, seed=args.seed, k=args.k)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=args.output.parent) as directory:
                    temporary_report = Path(directory) / args.output.name
                    temporary_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
                    temporary_report.replace(args.output)
            print(json.dumps(report, indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
