# Claude API Cost Optimization - Product Requirements Document

## Overview

This PRD defines the work required to analyze and optimize Claude API token usage and costs in the geelark-automation codebase. The goal is to systematically identify all factors driving high API costs and implement targeted optimizations to reduce token consumption while maintaining functionality.

## Background

The codebase uses Claude API for AI-driven Instagram posting automation. Early observations suggest high token usage due to:
- Full UI XML dumps being sent with each Claude call
- Repeated static system prompts without caching
- Single-action response patterns requiring multiple API calls per post
- Retry logic that rebuilds and resends full prompts
- Potential code duplication in prompt construction

## Goals

1. Reduce Claude API token usage by 50-80%
2. Reduce API cost per successful post
3. Maintain or improve posting success rates
4. Document all findings for future reference

---

## Phase 1: Generate Comprehensive Codebase Digest

### Objective
Create a complete, structured digest of the codebase with a strong focus on identifying factors that drive high Anthropic Claude API token usage and costs.

### Requirements

1. **Directory Traversal**
   - Traverse the entire codebase recursively with no depth limit
   - Ignore: .git, __pycache__, node_modules, venv, log files >100KB, binary files
   - Include only: .py, .json, .md, .txt, .yaml, .yml files

2. **File Metrics Collection**
   - For every included file collect:
     - Full relative path
     - File size in bytes
     - Line count
     - Estimated token count (characters / 4)

3. **Directory Structure Documentation**
   - Generate Markdown-formatted directory tree
   - Show all folders and included files

4. **Anthropic SDK Usage Analysis**
   - List all files that import or use Anthropic SDK
   - Search for: "anthropic", "client.messages", "client.beta", "messages.create"
   - Count obvious LLM API call sites

5. **Initial Cost Observations**
   - Identify files with loops that call LLM repeatedly
   - Find places where UI XML dumps are built and sent
   - Document retry logic that could multiply API calls

### Deliverable
A comprehensive Markdown document saved as `reviews/codebase_digest.md`

---

## Phase 2: Identify API Cost Bottlenecks

### Objective
Identify and prioritize every factor contributing to high Claude API token usage and costs.

### Requirements

1. **API Call Site Analysis**
   - Locate every Anthropic API call in the codebase
   - For each call site document:
     - File and line numbers
     - Whether inside a loop
     - Whether inside retry logic
     - What data is added to the prompt

2. **Token Size Estimation**
   - Count repeated static text (system instructions)
   - Estimate size of UI XML dumps
   - Note if full XML or filtered
   - Measure variable data (captions, state)

3. **Loop Analysis**
   - Identify all loops that drive repeated calls
   - Focus on: post_reel_smart.py, retry_manager.py, parallel_worker.py
   - Calculate calls per successful post

4. **Retry Behavior Documentation**
   - How many retries allowed
   - Whether retries rebuild full prompts
   - Token waste from retries

5. **UI Hierarchy Analysis**
   - Document all places where UI hierarchies are dumped
   - Measure XML size before/after any filtering

### Deliverable
A detailed Markdown report saved as `reviews/api_cost_bottlenecks.md` with:
- Summary of API Call Frequency
- Top 5 Bottlenecks Ranked by Estimated Token Impact
- Detailed Breakdown per bottleneck with file/line references
- Rough Daily Cost Projection (assume 100 posts/day)

---

## Phase 3: Analyze Code Duplication Contributing to Cost

### Objective
Identify duplicated or near-duplicated code that unnecessarily increases token usage.

### Requirements

1. **Duplication Detection**
   - Search for repeated code blocks longer than 10 lines
   - Focus on:
     - Prompt construction logic
     - UI XML filtering/parsing
     - Error handling and retry wrappers
     - State tracking JSON read/write

2. **Duplication Documentation**
   - For each significant duplication:
     - List exact file paths and line ranges
     - Describe duplicated code precisely
     - Explain how duplication contributes to higher token costs
     - Estimate potential token savings if refactored

3. **Prompt String Analysis**
   - Find copy-pasted system prompts
   - Find repeated instruction strings
   - Measure redundancy in prompt templates

### Deliverable
A Markdown report saved as `reviews/code_duplication_analysis.md` with:
- Overview: percentage of codebase affected by duplication
- Detailed Duplication Findings
- Projected Savings from DRY refactoring

---

## Phase 4: Propose Targeted Optimizations

### Objective
Propose concrete optimizations to reduce Claude API token usage and costs based on all previous analyses.

### Requirements

1. **Optimization Proposals**
   - For each optimization:
     - Describe the change clearly in 1-2 sentences
     - Reference exact files and locations
     - Estimate token savings per call, per post, percentage reduction
     - Estimate implementation effort (low/medium/high)
     - Note any risks or side effects

2. **Priority Techniques to Evaluate**
   - Aggressive UI XML compression/filtering (keep only tappable elements)
   - Using Anthropic prompt caching for static system instructions
   - Allowing Claude to return multiple actions in one response
   - Adding rule-based fallbacks for common Instagram screens
   - Extracting duplicated logic into shared utilities
   - Limiting retries and using simpler prompts on retry
   - Adding stability waits to reduce unnecessary UI dumps

3. **Prioritization**
   - Rank optimizations by impact (highest first)
   - Consider implementation effort vs. savings ratio

### Deliverable
A prioritized optimization plan saved as `reviews/optimization_proposals.md`

---

## Phase 5: Implement Specific Refactoring

### Objective
Implement the top 5 highest-impact optimizations as concrete code changes.

### Requirements

1. **Implementation Standards**
   - For each optimization:
     - State which optimization it addresses
     - Show exact files to modify
     - Provide complete before-and-after code
     - Include inline comments explaining token savings
     - Maintain all existing functionality

2. **Focus Areas**
   - Prompt caching integration
   - UI XML filtering/compression
   - Multi-action response support
   - Shared prompt-building utilities
   - Rule-based shortcuts for common screens

3. **Testing**
   - Each change must be testable
   - Document expected behavior changes
   - Provide verification steps

### Deliverables
- Modified source files with optimizations implemented
- Final summary report saved as `reviews/implementation_summary.md`

---

## Success Metrics

1. **Token Reduction**: Measure tokens per successful post before/after
2. **Cost Reduction**: Calculate cost savings at 100 posts/day
3. **Functionality**: All existing tests pass, posting success rate maintained
4. **Documentation**: Complete analysis trail in reviews/ folder

## Timeline

This is a research and implementation task requiring:
- Phase 1-3: Analysis and documentation
- Phase 4: Planning
- Phase 5: Implementation

## Dependencies

- Access to full codebase
- Claude API usage data (if available)
- Understanding of Anthropic prompt caching API
