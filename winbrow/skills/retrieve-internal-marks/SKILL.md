---
name: "retrieve-internal-marks"
skill: "playbook_retrieve_internal_marks"
kind: playbook
args:
  - name: "portal_url"
    type: "string"
    required: true
    default: null
    description: "Base URL of the student portal (e.g., https://college.etlab.in)."
  - name: "semester"
    type: "string"
    required: true
    default: null
    description: "Semester to retrieve marks for, e.g., 'Ist Semester', 'IInd Semester'."
  - name: "result_type"
    type: "string"
    required: false
    default: "Internal Marks"
    description: "Type of result to fetch, e.g., 'Internal Marks', 'University Result'."
description: >
  Use this skill to retrieve internal marks from an etlab-based student
  portal. It navigates to the results page, selects the internal marks option,
  chooses the specified semester, and reads the displayed marks. Do not use
  for other result types like university results or attendance.
---

## When to Use

When the user asks to fetch internal marks or similar result data from an etlab-based student portal, and the portal URL and semester are known or can be provided.

## When NOT to Use

Do not use for non-etlab portals, for attendance or other non-result data, or when the portal layout has changed significantly and the steps no longer apply.

## Step Pattern

1. Navigate to the student portal at {portal_url}.
2. Navigate to the results page (typically at /student/results).
3. Click on the {result_type} link.
4. Select {semester} from the semester dropdown.
5. Read the page to extract the marks.

## Args Detail

- `portal_url` (string, required): Base URL of the student portal (e.g., https://college.etlab.in).
- `semester` (string, required): Semester to retrieve marks for, e.g., 'Ist Semester', 'IInd Semester'.
- `result_type` (string, default='Internal Marks'): Type of result to fetch, e.g., 'Internal Marks', 'University Result'.

## Output Shape

Returns a result dict with `success`, `output`, and any state fields the
chosen tool provides. A successful step means the tool dispatched the action;
it does not by itself prove the wider goal is complete. Verify with the next
read step before declaring the task done.

## Recovery

If the results page does not load or the dropdown is unresponsive, refresh the page and retry. Use the accessibility tree to locate the correct interactive elements if selectors fail. If the semester selection does not take effect, try selecting a different value or using keyboard input. If the result type link is not visible, check for alternative navigation paths.
