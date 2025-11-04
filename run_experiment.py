import argparse
import json
import os

import doc_agent
import doc_reader

parser = argparse.ArgumentParser(description="Run experiment")
parser.add_argument(
    "--api-key",
    type=str,
    default=os.getenv("OPENAI_API_KEY", "sk-proj-XXXXXXXXXXXXXXXXXXXXXX"),
    help="API key (or set OPENAI_API_KEY env var)",
)
parser.add_argument(
    "--save-dir",
    type=str,
    default="./sample_results/",
    help="Directory to save results",
)
parser.add_argument(
    "--preprocessed-data-dir",
    type=str,
    default="./preprocess/processed_output/",
    help="Preprocessed data directory",
)
parser.add_argument(
    "--raw-data-dir",
    type=str,
    default="./sample_data/",
    help="Raw data directory",
)
args = parser.parse_args()


def main(args):
    os.makedirs(args.save_dir, exist_ok=True)

    dataset = sorted(os.listdir(args.raw_data_dir))

    # initialize empty memory
    memory = ""

    for index in range(len(dataset)):

        sample = json.load(
            open(os.path.join(args.raw_data_dir, dataset[index], "sample.json"))
        )
        doc_id = sample["doc_id"][:-4]

        save_path = os.path.join(args.save_dir, "job_" + str("%05d" % index) + ".json")
        if os.path.exists(save_path):
            continue
        result = {"doc_id": doc_id}
        print("Processing", index)

        # load document and initialize agent
        document = doc_reader.DocReader(
            data_path=os.path.join(args.preprocessed_data_dir, doc_id)
        )
        agent = doc_agent.DocAgent(document, model_id="gpt-4o", api_key=args.api_key)

        # run actor loop
        final_response, messages = agent.run_actor(
            question=sample["question"], memory=memory
        )

        result["actor_response"] = final_response
        result["actor_messages"] = messages

        # run reviewer loop
        final_response_reviewer, messages_reviewer = agent.run_reviewer(
            initial_messages=result["actor_messages"]
        )

        result["reviewer_response"] = final_response_reviewer
        result["reviewer_messages"] = messages_reviewer[len(result["actor_messages"]) :]

        if final_response_reviewer != final_response:
            # update memory with reflection loop
            initial_messages = result["actor_messages"] + result["reviewer_messages"]
            memory, reflection_messages = agent.run_reflection(
                initial_messages=initial_messages, memory=memory
            )

            result["reflection_messages"] = reflection_messages[len(initial_messages) :]

        result["memory"] = memory

        with open(save_path, "w") as f:
            json.dump(result, f, indent=4)


if __name__ == "__main__":
    main(args)
