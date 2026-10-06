"""
Values of global configuration variables.
"""

# Overall output directory for results
output_dir: str = ""

# Max number of times context retrieval and all is tried
overall_retry_limit: int = 3

# upper bound of the number of conversation rounds for the agent
conv_round_limit: int = 10

# upper bound of the number of conversation rounds for reproduction
reproduce_round_limit: int = 5

# whether to perform sbfl
enable_sbfl: bool = False

# whether to perform our own validation
enable_validation: bool = False

# whether to do angelic debugging
enable_angelic: bool = False

# whether to do perfect angelic debugging
enable_perfect_angelic: bool = False


# A special mode to only save SBFL result and exit
only_save_sbfl_result: bool = False

# A special mode to only generate reproducer tests and exit
only_reproduce: bool = False

# Memory gate mode: "none", "baseline", "gated", "gated-provenance", "gated-execution"
memory_mode: str = "baseline"

# Stream-order cutoff for memory retrieval (ISO date, e.g. "2019-01-30T13:13:20Z")
# Only entries with created_at earlier than this are loaded by save_experiences.
current_created_at: str = ""

# A special mode to only evaluate a reproducer test
only_eval_reproducer: bool = False

# Experimental mode to add reproducer and reviewer into the workflow
reproduce_and_review: bool = True

# timeout for test cmd execution, currently set to 5 min
test_exec_timeout: int = 300

models: list[str] = []

backup_model = ["gpt-4o-2024-05-13"]
# backup_model = ["gpt-3.5-turbo"]

disable_angelic: bool = False
