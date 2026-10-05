import argparse
import os
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-dir", type=str, default="results/validation_example",
                        help="Directory holding <repo>/<task_id>/ranked_final_patch.jsonl files.")
    parser.add_argument("--repos", type=str, nargs="*", default=None,
                        help="Repos to collect. Defaults to the full hardcoded list.")
    parser.add_argument("--task-list-file", type=str, default=None,
                        help="Only collect tasks listed in this file (one id per line).")
    parser.add_argument("--preds-file", type=str, default="results/preds_example/final_0.jsonl",
                        help="Output predictions file (overwritten).")
    args = parser.parse_args()

    default_repos = ['astropy', 'flask', 'pylint', 'pytest', 'requests', 'scikit-learn', 'seaborn', 'sphinx', 'xarray', 'django', 'sympy', 'matplotlib']
    repo_list = args.repos if args.repos else default_repos

    only_tasks = None
    if args.task_list_file is not None:
        with open(args.task_list_file) as f:
            only_tasks = {line.strip() for line in f if line.strip()}

    generated_patch = {}
    for repo_name in repo_list:
    # repo_name = 'django'
        directory = f"{args.validation_dir}/{repo_name}"
        if not os.path.isdir(directory):
            print(f"Skipping {repo_name}: {directory} not found.")
            continue


        for task_id in os.listdir(directory):
            if only_tasks is not None and task_id not in only_tasks:
                continue
            # if task_id not in ['psf__requests-2148', ...]:
            #     continue
            with open(directory + '/' + task_id + '/ranked_final_patch.jsonl', 'r', encoding='utf-8') as f:
                data_lines = f.readlines()

            patch_list = [json.loads(data_line)['model_patch'] for data_line in data_lines]
            generated_patch[task_id] = patch_list


    print(len(generated_patch.keys()))

    os.makedirs(os.path.dirname(args.preds_file) or ".", exist_ok=True)
    for task_id in generated_patch.keys():
        patch_list = generated_patch[task_id]
        for num_idx in list(range(len(patch_list)))[:1]:
            with open(args.preds_file, 'a') as w:
                w.write(
                    json.dumps(
                        {
                            "model_name_or_path": f"ase_{num_idx}",
                            "instance_id": task_id,
                            "model_patch": patch_list[num_idx],
                        }
                    )
                    + "\n"
                )
