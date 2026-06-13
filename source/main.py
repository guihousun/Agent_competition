from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from source.runtime.batch_runner import BatchRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Skill distillation contest demo runner")
    parser.add_argument(
        "--question",
        required=True,
        help="Path to question JSON file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to output result JSON file.",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Write a live local dashboard next to the result file.",
    )
    return parser.parse_args()


async def amain() -> None:
    args = parse_args()
    runner = BatchRunner()
    results = await runner.run_file(
        question_path=Path(args.question),
        output_path=Path(args.output),
        dashboard=args.dashboard,
    )
    print(f"done: {len(results)} answers written")
    print(f"result saved to: {Path(args.output).resolve()}")


if __name__ == "__main__":
    asyncio.run(amain())
