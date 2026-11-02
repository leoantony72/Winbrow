---
name: find-files
skill: find_files
args:
  - name: search_term
    type: string
    required: false
    default: "*"
    description: File or folder name (or fragment) to search for in the Everything index.
description: >
  Find a file OR folder by name with Everything (es.exe). WinBrow installs and
  starts a portable Everything instance on first launch, so this searches every
  indexed drive instead of only Desktop, Documents, Downloads or Pictures.
  Folder matches are returned as [folder] paths. Use first for any name lookup,
  including "find the X folder", fuzzy variants of a spoken name, and case
  differences (search is case-insensitive).
---

## When to Use

Use at the start of any task that needs an existing path: opening, moving,
uploading, copying, renaming, inspecting a file, or locating a folder. It is
fast because it queries the Everything index; it does not walk user folders.

## When NOT to Use

- Do not use it when CONVERSATION or HISTORY already contains the exact path.
- Do not use it to search inside file contents; use run-command with a content
  search only when no dedicated skill exists.
- Do not use `run_command`, `mcp_filesystem_list_directory`, or a recursive
  `Get-ChildItem` to find a file or folder by name. This skill already does
  that through Everything, including folders (`D:\Codee\pcc`).
- Do not turn it into a raw recursive folder or drive scan when Everything
  returns no hit. Ask for the location or full path instead.
- Do not search the same term more than twice before asking the user.

## Step Pattern

Follow this escalation and stop as soon as the item is found:

1. If a matching path is already in CONVERSATION or HISTORY, use it directly.
2. Otherwise search the exact name the user gave. The tool queries Everything
   `es.exe` for folders first, then files, across all indexed drives. Search is
   case-insensitive; the portable WinBrow instance is started automatically.
3. If nothing is found, search a fuzzy variant: drop spaces, add spaces, use
   underscores, use lowercase (for example "LDMseminar" becomes "LDM seminar",
   "ldm_seminar", "LDM_seminar").
4. If still nothing, emit clarify with the searched source and ask for the
   location or full path.
5. Once a path is returned, pass that exact path to open-file, move-file,
   browser-upload-file or create-text-file. For a folder path, use open-folder.

## Args Detail

- `search_term` is the exact name or a fragment. Wildcards are accepted; the
  default `*` lists everything, which is rarely useful.
- Results always come from Everything and can include both files and folders.
  Folder rows look like `[folder] D:\Codee\pcc`; file rows include a size.
  The tool never walks Desktop, Documents, Downloads or Pictures and does not
  query Windows Search.
- If more than one entry is plausible, list the candidates and emit clarify
  instead of guessing.

## Output Shape

Returns `success`, `output` (matching paths, one per line) and may include a
`files` list. The output names the source (`Everything`) and marks folders with
`[folder]`. A "No matches" output means Everything answered the query; it is
authoritative for the drives Everything has indexed.

## Recovery

After an empty result, try one fuzzy variant, then clarify. Never repeat the
same search a third time. If a result is ambiguous, ask which entry the user
means and retain the chosen path in HISTORY for the next step. If a drive is
unindexed or Everything is still building its first index, tell the user to
wait a minute and retry, or provide the full path; do not silently launch a
slow folder or drive scan with `run_command`.
