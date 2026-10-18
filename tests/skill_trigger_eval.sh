#!/usr/bin/env bash
# Evaluate whether the skill triggers on relevant prompts and ignores near misses.
# The name "askance" carries no statistical meaning, so the description must do the routing.
# Usage: tests/skill_trigger_eval.sh [runs] [main|holdout]   (default 1 main)
set -uo pipefail

RUNS="${1:-1}"
SET="${2:-main}"
MARKER="skill(askance)"
PARALLEL=4

# Positives avoid explicit statistical terms; those prompts would be too easy.
MAIN=(
"yes|ab-counts|I ran our checkout A/B test for two weeks. Variant A converted 84 of 1200 visitors, variant B 112 of 1180. Did B actually win?"
"yes|paired-latency|Response times before and after the cache change on the same 8 boxes: [212,198,225,240,201,233,219,208] then [190,185,201,219,188,207,196,191]. Is that a real improvement or just noise?"
"yes|cohorts-casual|my manager wants to know if the new onboarding actually helped retention. old cohort: [12,15,9,22,18,14], new cohort: [19,23,17,28,21,25]. can you tell?"
"yes|three-groups|We tried 3 compiler flag sets on the same benchmark. A [4.2,4.5,4.1], B [3.8,3.9,4.0], C [4.6,4.4,4.7]. Is any of them actually faster?"
"yes|correlation|Is there a relationship between our deploy frequency [3,7,2,9,5,8] and incident count [1,4,1,5,2,4]?"
"yes|flag-rate|I flipped our feature flag for 200 users and 118 clicked through. Baseline click rate is 50%. Is that meaningfully above baseline?"
# Near misses share vocabulary with the skill but require a different task.
"no|plot|Plot the distribution of these latency numbers as a histogram: [212,198,225,240,201,233,219,208]"
"no|profile|Why is this benchmark so slow? Here is the profile output showing 80% of time in json.loads"
"no|write-stats-fn|Write a python function that computes the mean and standard deviation of a list of floats"
"no|summarize|Summarize the key findings in this quarterly sales CSV: Q1 120k, Q2 135k, Q3 128k, Q4 160k"
"no|failing-tests|Our test suite has 3 failing tests after the refactor, can you fix them"
"no|explain-p|Explain what a p-value actually means to a non-technical stakeholder"
)

# This set was written after the first description was finalized. The power-analysis query
# changed from negative to positive when analyze_power shipped.
HOLDOUT=(
"yes|ship-it|We shipped the new ranking model to half our users last month. Control averaged 4.2 sessions per user, treatment 4.6, about 900 users in each arm. Ship it or roll back?"
"yes|settle-argument|Two people on my team disagree about whether their refactor made the parser faster. Ten timing runs each: old [1.42,1.38,1.51,1.45,1.39,1.48,1.44,1.41,1.50,1.43] new [1.31,1.29,1.35,1.28,1.33,1.30,1.36,1.32,1.27,1.34]. Settle it."
"yes|survey-ordinal|I have 1-5 helpfulness scores from 12 users on the old help page [3,4,2,3,5,3,4,2,3,4,3,2] and 12 on the rewrite [4,5,4,5,3,4,5,4,4,5,3,4]. Did the rewrite land?"
"yes|tea-leaves|Our error rate was 31 failures out of 1000 requests last week and 24 out of 1000 this week. Are we actually improving or am I reading tea leaves?"
"yes|power-analysis|What sample size would I need for an A/B test to reliably detect a 2 percent lift in conversion?"
"no|descriptive|Calculate the average and median of these build times: [12,15,9,22,18]"
"no|postmortem|Our latency SLO is 200ms and we came in at 340ms yesterday. Draft the incident postmortem."
"no|sql-group|Write a SQL query that groups orders by region and compares this quarter's revenue to last quarter's"
)

case "$SET" in
  main) QUERIES=("${MAIN[@]}") ;;
  holdout) QUERIES=("${HOLDOUT[@]}") ;;
  *) echo "unknown set: $SET (use main or holdout)" >&2; exit 2 ;;
esac

run_one() {
  local expect="$1" label="$2" query="$3" hits=0
  for _ in $(seq 1 "$RUNS"); do
    if timeout 300 copilot -p "$query" --allow-all-tools 2>&1 | grep -qF "$MARKER"; then
      hits=$((hits + 1))
    fi
  done
  local rate verdict
  rate=$(awk -v h="$hits" -v r="$RUNS" 'BEGIN{printf "%.2f", h/r}')
  if [ "$expect" = yes ]; then
    awk -v x="$rate" 'BEGIN{exit !(x > 0.5)}' && verdict=PASS || verdict=FAIL
  else
    awk -v x="$rate" 'BEGIN{exit !(x <= 0.5)}' && verdict=PASS || verdict=FAIL
  fi
  printf '%-4s expect=%-3s rate=%s  %s\n' "$verdict" "$expect" "$rate" "$label"
}

export -f run_one
export RUNS MARKER

printf 'Running %s set: %d queries x %d run(s)\n\n' "$SET" "${#QUERIES[@]}" "$RUNS"
# NUL-separated and passed as an argument: xargs would otherwise strip quotes such as the
# apostrophes in "quarter's", and splicing the query into the script would let it run as code.
printf '%s\0' "${QUERIES[@]}" \
  | xargs -0 -n 1 -P "$PARALLEL" bash -c 'IFS="|" read -r e l q <<< "$1"; run_one "$e" "$l" "$q"' _ \
  | sort -k4 | tee /tmp/askance_eval.txt

echo
awk '{print $1}' /tmp/askance_eval.txt | sort | uniq -c
