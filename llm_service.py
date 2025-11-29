import argparse
from typing import List

from transformers import pipeline


def generate_responses(prompt: str, max_new_tokens: int, num_return_sequences: int) -> List[str]:
    generator = pipeline("text-generation", model="distilgpt2")
    outputs = generator(
        prompt,
        max_new_tokens=max_new_tokens,
        num_return_sequences=num_return_sequences,
        do_sample=True,
        top_p=0.95,
        temperature=0.8,
    )
    return [out["generated_text"] for out in outputs]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple local LLM demo using distilgpt2.")
    parser.add_argument("--prompt", required=True, help="Prompt to generate text from.")
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=64,
        help="Maximum number of tokens to generate.",
    )
    parser.add_argument(
        "--num-return-sequences",
        type=int,
        default=1,
        help="How many alternative generations to produce.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    responses = generate_responses(
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        num_return_sequences=args.num_return_sequences,
    )
    for idx, text in enumerate(responses, 1):
        print(f"\n=== Response {idx} ===\n{text}")


if __name__ == "__main__":
    main()
