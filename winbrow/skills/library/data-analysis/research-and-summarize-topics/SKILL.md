---
name: research-and-summarize-topics
skill: playbook_research_and_summarize_topics
kind: playbook
category: data-analysis
args: []
description: >
  Use this skill when the user asks to research multiple distinct topics
  and produce a summary for each. It performs web searches and fetches
  authoritative pages for each topic, then compiles a concise summary. Do
  not use for a single topic deep dive or for tasks that require analysis
  beyond summarization.
---

## When to Use

When the user requests summaries for two or more distinct topics, festivals, events, or concepts that require external research.

## When NOT to Use

When only one topic is involved, when the user wants a deep analysis or comparison rather than summaries, or when the topics are already known and no research is needed.

## Step Pattern

1. For each topic in the topics list: 2. Perform a web search using the topic name and relevant keywords (e.g., 'history significance highlights'). 3. Select the most authoritative result (e.g., Wikipedia) and fetch the page, focusing on key aspects like history, significance, rituals, and traditions. 4. Extract the essential facts and details from the fetched content. 5. Compile a concise summary for that topic. 6. After processing all topics, present the summaries together, clearly separated by topic.

## Args Detail

- `topics` (string, required): List of topics to research and summarize. Each topic is a string, e.g., ['Thrissur Pooram', 'Diwali'].

## Output Shape

Returns a result dict with `success`, `output`, and any state fields the
chosen tool provides. A successful step means the tool dispatched the action;
it does not by itself prove the wider goal is complete. Verify with the next
read step before declaring the task done.

## Recovery

If a web search returns no useful results, try alternative queries with different keywords. If a fetch fails, attempt another authoritative source from the search results. If a topic is obscure, broaden the search terms or use a general encyclopedia.
