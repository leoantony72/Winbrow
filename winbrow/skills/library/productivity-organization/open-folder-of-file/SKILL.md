---
name: open-folder-of-file
skill: playbook_open_folder_of_file
kind: playbook
category: productivity-organization
args: []
description: >
  Use this skill when the user wants to open the folder where a specific
  file is located, but the exact path is unknown. It searches for files by
  a search term and opens the folder containing the first match. Do not
  use for opening a known folder path; use the open-folder skill instead.
---

## When to Use

When the user asks to open the folder containing a file, and the folder path is not known or not provided.

## When NOT to Use

When the user provides an explicit folder path to open, or when the file is already known and its folder is obvious.

## Step Pattern

1. Call find_files with the search_term.
2. If no files are found, report that no files match and ask for a different term.
3. If files are found, take the first file's path and extract its directory.
4. Call open_folder with that directory.
5. If open_folder fails, report the error.

## Args Detail

- `search_term` (string, required): The term to search for in file names, e.g. a filename fragment or keyword.

## Output Shape

Returns a result dict with `success`, `output`, and any state fields the
chosen tool provides. A successful step means the tool dispatched the action;
it does not by itself prove the wider goal is complete. Verify with the next
read step before declaring the task done.

## Recovery

If find_files returns no results, suggest trying a different search term. If open_folder fails, verify the directory exists and try again.
