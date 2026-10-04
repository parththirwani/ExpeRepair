#!/bin/bash
# Usage:
#   SETUP_MAP_PATH=/path/to/setup_map.json TASKS_MAP_PATH=/path/to/tasks_map.json \
#   OUTPUT_DIR=results REPRODUCE_DIR=results/reproduce_example \
#   LOCALIZE_DIR=results/localize_example MODEL=gpt-5.6-luna \
#   bash inference/run_generate.sh [task_id ...]
# First task in the list runs generate_initial.py (no memory);
# remaining tasks run generate_w_memory.py (with memory).

MODEL="${MODEL:-gpt-5.6-luna}"
SETUP_MAP="${SETUP_MAP_PATH:-./setup_map.json}"
TASKS_MAP="${TASKS_MAP_PATH:-./tasks_map.json}"
OUTPUT_DIR="${OUTPUT_DIR:-results/generate_example}"
REPRODUCE_DIR="${REPRODUCE_DIR:-results/reproduce_example}"
LOCALIZE_DIR="${LOCALIZE_DIR:-results/localize_example}"

if [ "$#" -gt 0 ]; then
    task_ids=("$@")
else
    task_ids=("django__django-10914" "django__django-12708")
fi

# First task: no memory (baseline)
first_task="${task_ids[0]}"
echo "Running task with task_id: $first_task (generate_initial, model=$MODEL)"
python inference/generate_initial.py --model "$MODEL" \
--setup-map "$SETUP_MAP" \
--tasks-map "$TASKS_MAP" \
--output_folder "$OUTPUT_DIR" \
--reproduce_folder "$REPRODUCE_DIR" \
--localize_folder "$LOCALIZE_DIR" \
--task_id "$first_task"

# Remaining tasks: with memory
for task_id in "${task_ids[@]:1}"; do
    echo "Running task with task_id: $task_id (generate_w_memory, model=$MODEL)"
    python inference/generate_w_memory.py --model "$MODEL" \
    --setup-map "$SETUP_MAP" \
    --tasks-map "$TASKS_MAP" \
    --output_folder "$OUTPUT_DIR" \
    --reproduce_folder "$REPRODUCE_DIR" \
    --localize_folder "$LOCALIZE_DIR" \
    --task_id "$task_id"
done
