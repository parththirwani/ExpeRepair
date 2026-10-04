#!/bin/bash
# Usage:
#   SETUP_MAP_PATH=/path/to/setup_map.json TASKS_MAP_PATH=/path/to/tasks_map.json \
#   OUTPUT_DIR=results REPRODUCE_DIR=results/reproduce_example \
#   MODEL=gpt-5.6-luna bash inference/run_localization.sh [task_id ...]

MODEL="${MODEL:-gpt-5.6-luna}"
SETUP_MAP="${SETUP_MAP_PATH:-./setup_map.json}"
TASKS_MAP="${TASKS_MAP_PATH:-./tasks_map.json}"
OUTPUT_DIR="${OUTPUT_DIR:-results/localize_example}"
REPRODUCE_DIR="${REPRODUCE_DIR:-results/reproduce_example}"

if [ "$#" -gt 0 ]; then
    task_ids=("$@")
else
    task_ids=("django__django-10914" "django__django-12708")
fi

# Iterate over each task_id and run the command
for task_id in "${task_ids[@]}"; do
    echo "Running task with task_id: $task_id (model=$MODEL)"
    python inference/localize.py --model "$MODEL" \
    --setup-map "$SETUP_MAP" \
    --tasks-map "$TASKS_MAP" \
    --output_folder "$OUTPUT_DIR" \
    --reproduce_folder "$REPRODUCE_DIR" \
    --task_id "$task_id"
done
