import json
import asyncio
from search_engine import SearchEngine
from semantic_processor import SemanticProcessor

# Path to the baseline results file
BASELINE_PATH = "/Users/navinsharma/Desktop/baseline_results.jsonl"
OUTPUT_PATH = "evaluation_results.jsonl"

async def evaluate():
    # Load baseline questions
    with open(BASELINE_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    questions = [json.loads(line) for line in lines if line.strip()]

    search_engine = SearchEngine()
    semantic_processor = SemanticProcessor()
    results = []

    for q in questions:
        question = q["question"]
        ground_truth = q.get("ground_truth", "")
        contexts = q.get("contexts", [])
        question_type = q.get("question_type", "")

        # Use the app's search and summarization pipeline
        search_results = await search_engine.search(question, max_results=10)
        summary_result = await semantic_processor.summarize_content(search_results, question)
        answer = summary_result.get("summary", "")

        results.append({
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "ground_truth": ground_truth,
            "question_type": question_type
        })
        print(f"Evaluated: {question}")

    # Write results to output file
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"Evaluation complete. Results saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(evaluate()) 