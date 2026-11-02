---
name: create-text-file
skill: create_text_file
args:
  - name: filename
    type: string
    required: true
    description: File name including the extension, e.g. notes.txt.
  - name: content
    type: string
    required: true
    description: Exact text to write into the file.
  - name: folder
    type: string
    required: false
    default: Desktop
    description: Desktop, Documents, Downloads, Pictures, Videos, a relative subfolder under the user profile (e.g. Desktop\deck), or any absolute folder path (e.g. D:\projects\deck). Windows system folders and the WinBrow app folder are never deliverable targets.
description: >
  Create a named text file with exact content in any user-writable folder, from
  a known alias to a full absolute path. Use for notes, code snippets and small
  documents the user asks you to save. Only Windows system folders are refused.
---

## When to Use

Use when the user asks for a named text file and the content is already known or
produced by the current task. It is the correct skill for `notes.txt`,
`chicken.go` or a report in a common folder, a nested project folder, or any
absolute path such as `D:\projects\deck\slides\index.html`.

## When NOT to Use

- Do not use it for a quick note that should open in Notepad; use quick-note.
- Do not use it for binary files, downloads or images.
- Do not use it when the user wants a folder created; use the filesystem
  create-directory tool or run-command.
- Do not write into Windows, Program Files, ProgramData or other system-owned
  folders; the tool refuses those.

## Step Pattern

1. Resolve the target folder and filename from GOAL and HISTORY.
2. Call create-text-file with `filename`, `content` and `folder`. `folder` may
   be Desktop/Downloads/Documents/Pictures/Videos, a subfolder such as
   `Desktop\chicken-go`, or an absolute path.
3. Read the file back with open-file or the filesystem read tool when the task
   requires verification.
4. For code, follow with run-command to build or test before declaring done.

## Args Detail

- `filename` must include an extension; a bare name may be rejected or saved
  without one. A full path in `filename` is also accepted.
- `content` is written verbatim. Preserve newlines, quotes and code exactly;
  do not add commentary.
- `folder` accepts a known alias or any real path. Use Desktop when the user
  says "on my desktop" or gives no folder.
- If create-text-file fails, read the error before retrying; do not repeat the
  same call. Only Windows system folders are intentionally refused.

## Output Shape

Returns `success`, `output` (the created path) and the file metadata. Success
means the file was written; if the task requires the program to run, that is a
separate verification step.

## Recovery

If the write fails, check the folder name and filename, then retry once with
the full-path filesystem write tool. If the file already exists and the user
did not ask to overwrite, clarify or choose a new name. Never claim the file
exists without a successful result or a read-back. Follow the self-correct
rule.
