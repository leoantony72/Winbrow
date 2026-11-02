import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Plus,
  RefreshCw,
  Save,
  Search,
} from "lucide-react";
import { apiGet, apiPost } from "./lib/agent";

interface EnvField {
  key: string;
  label: string;
  description: string;
  kind: "text" | "number" | "boolean" | "select";
  choices: string[];
  restart: boolean;
  secret: boolean;
  value: string;
  default: string;
  source: "env" | "process" | "default";
  is_set: boolean;
  in_file: boolean;
}

interface EnvGroup {
  id: string;
  label: string;
  description: string;
  fields: EnvField[];
}

interface EnvConfig {
  path: string;
  groups: EnvGroup[];
  custom: EnvField[];
  secrets_stored_plaintext?: boolean;
}

interface SaveResult {
  status: string;
  saved: string[];
  unset: string[];
  requires_restart: boolean;
  restart_keys: string[];
}

const KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function truthy(value: string): boolean {
  return !["", "0", "false", "no", "off"].includes(value.trim().toLowerCase());
}

function fieldBase(field: EnvField): string {
  if (field.kind === "boolean") return truthy(field.value) ? "1" : "0";
  return field.value;
}

function draftFromConfig(config: EnvConfig): Record<string, string> {
  const draft: Record<string, string> = {};
  for (const group of config.groups) {
    for (const field of group.fields) draft[field.key] = fieldBase(field);
  }
  for (const field of config.custom) draft[field.key] = fieldBase(field);
  return draft;
}

function allFields(config: EnvConfig): EnvField[] {
  return [...config.groups.flatMap((group) => group.fields), ...config.custom];
}

export default function Settings({ onRestart }: { onRestart?: () => void }) {
  const [config, setConfig] = useState<EnvConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [unset, setUnset] = useState<Set<string>>(() => new Set());
  const [filter, setFilter] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [restartKeys, setRestartKeys] = useState<string[]>([]);
  const [customKey, setCustomKey] = useState("");
  const [customValue, setCustomValue] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await apiGet<EnvConfig>("/api/env");
      setConfig(data);
      setDraft(draftFromConfig(data));
      setUnset(new Set());
      setError("");
    } catch (exc) {
      setError(`Could not load settings: ${String(exc)}`);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const fields = useMemo(() => (config ? allFields(config) : []), [config]);
  const fieldMap = useMemo(() => {
    const map = new Map<string, EnvField>();
    for (const field of fields) map.set(field.key, field);
    return map;
  }, [fields]);

  const dirty = useMemo(() => {
    if (!config) return false;
    if (unset.size) return true;
    return fields.some((field) => {
      const next = draft[field.key] ?? "";
      if (field.secret) return next.trim().length > 0;
      return next !== fieldBase(field);
    });
  }, [config, draft, fields, unset]);

  const update = (key: string, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const clearField = (key: string) => {
    setUnset((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    setDraft((prev) => ({ ...prev, [key]: "" }));
  };

  const undoField = (key: string, field: EnvField) => {
    setUnset((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    setDraft((prev) => ({ ...prev, [key]: fieldBase(field) }));
  };

  const save = async () => {
    if (!config || !dirty) return;
    const updates: Record<string, string> = {};
    for (const field of fields) {
      const next = draft[field.key] ?? "";
      if (unset.has(field.key)) continue;
      if (field.secret) {
        if (next.trim()) updates[field.key] = next;
        continue;
      }
      if (next !== fieldBase(field)) updates[field.key] = next;
    }
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const result = await apiPost<SaveResult>("/api/env", {
        updates,
        unset: [...unset],
      });
      setRestartKeys(result.requires_restart ? result.restart_keys : []);
      setMessage(
        `Saved ${result.saved.length + result.unset.length} change${
          result.saved.length + result.unset.length === 1 ? "" : "s"
        }.`,
      );
      await load();
    } catch (exc) {
      setError(`Could not save settings: ${String(exc)}`);
    } finally {
      setSaving(false);
    }
  };

  const addCustom = async () => {
    const key = customKey.trim();
    if (!KEY_RE.test(key)) {
      setError("Variable names use letters, digits and underscore, and cannot start with a digit.");
      return;
    }
    if ([...fieldMap.keys()].includes(key)) {
      setError(`${key} is already listed above.`);
      return;
    }
    setSaving(true);
    setMessage("");
    setError("");
    try {
      await apiPost<SaveResult>("/api/env", {
        updates: { [key]: customValue },
        unset: [],
      });
      setCustomKey("");
      setCustomValue("");
      setMessage(`Added ${key}.`);
      await load();
    } catch (exc) {
      setError(`Could not add ${key}: ${String(exc)}`);
    } finally {
      setSaving(false);
    }
  };

  const visibleGroups = config
    ? config.groups
        .map((group) => ({
          ...group,
          fields: group.fields.filter((field) => {
            if (!filter.trim()) return true;
            const needle = filter.trim().toLowerCase();
            return (
              field.key.toLowerCase().includes(needle) ||
              field.label.toLowerCase().includes(needle) ||
              field.description.toLowerCase().includes(needle)
            );
          }),
        }))
        .filter((group) => group.fields.length > 0)
    : [];
  const visibleCustom = config
    ? config.custom.filter((field) => {
        if (!filter.trim()) return true;
        const needle = filter.trim().toLowerCase();
        return (
          field.key.toLowerCase().includes(needle) ||
          field.label.toLowerCase().includes(needle)
        );
      })
    : [];

  if (!config) {
    return (
      <div className="settings">
        <div className="settings-empty">
          {error ? error : <><span className="pulse" /> Loading settings…</>}
        </div>
      </div>
    );
  }

  return (
    <div className="settings">
      <div className="task-head settings-head">
        <div className="task-title">
          <span className="status-text status-running">env</span>
          <h1>Settings</h1>
          <div className="settings-sub">
            Edit <code>{config.path}</code> from the app. Saved values apply to
            the running sidecar immediately where possible.
          </div>
        </div>
        <div className="settings-actions">
          <button
            type="button"
            className="btn"
            onClick={() => void load()}
            disabled={saving}
            title="Reload values from .env"
          >
            Reload
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void save()}
            disabled={!dirty || saving}
          >
            <Save size={13} aria-hidden /> {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="settings-scroll">
        <div className="settings-toolbar">
          <label className="settings-search">
            <Search size={14} aria-hidden />
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter variables…"
              aria-label="Filter environment variables"
            />
          </label>
          <span className="settings-note">
            <AlertTriangle size={13} aria-hidden /> Secrets are stored in plain
            text in <code>.env</code> on this PC.
          </span>
        </div>

        {message ? (
          <div className="settings-message settings-ok">
            <Check size={14} aria-hidden /> {message}
          </div>
        ) : null}
        {error ? (
          <div className="settings-message settings-bad">{error}</div>
        ) : null}
        {restartKeys.length ? (
          <div className="settings-message settings-warn">
            <RefreshCw size={14} aria-hidden />
            <span>
              Restart the sidecar to apply: <code>{restartKeys.join(", ")}</code>
            </span>
            <button
              type="button"
              className="btn"
              onClick={() => {
                onRestart?.();
                window.winbrow?.restartSidecar();
              }}
            >
              Restart now
            </button>
          </div>
        ) : null}

        {visibleGroups.map((group) => (
          <section className="settings-group" key={group.id}>
            <div className="settings-group-head">
              <h2>{group.label}</h2>
              <p>{group.description}</p>
            </div>
            <div className="settings-fields">
              {group.fields.map((field) => (
                <EnvRow
                  key={field.key}
                  field={field}
                  value={draft[field.key] ?? ""}
                  removed={unset.has(field.key)}
                  onChange={(value) => update(field.key, value)}
                  onClear={() => clearField(field.key)}
                  onUndo={() => undoField(field.key, field)}
                />
              ))}
            </div>
          </section>
        ))}

        <section className="settings-group">
          <div className="settings-group-head">
            <h2>Custom variables</h2>
            <p>Any other key/value pair written to .env.</p>
          </div>
          <div className="settings-fields">
            {visibleCustom.map((field) => (
              <EnvRow
                key={field.key}
                field={field}
                value={draft[field.key] ?? ""}
                removed={unset.has(field.key)}
                onChange={(value) => update(field.key, value)}
                onClear={() => clearField(field.key)}
                onUndo={() => undoField(field.key, field)}
              />
            ))}
            <div className="settings-custom-add">
              <input
                value={customKey}
                onChange={(event) => setCustomKey(event.target.value)}
                placeholder="NEW_VARIABLE"
                aria-label="New variable name"
                spellCheck={false}
              />
              <input
                value={customValue}
                onChange={(event) => setCustomValue(event.target.value)}
                placeholder="value"
                aria-label="New variable value"
              />
              <button
                type="button"
                className="btn"
                onClick={() => void addCustom()}
                disabled={!customKey.trim() || saving}
              >
                <Plus size={13} aria-hidden /> Add
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function EnvRow({
  field,
  value,
  removed,
  onChange,
  onClear,
  onUndo,
}: {
  field: EnvField;
  value: string;
  removed: boolean;
  onChange: (value: string) => void;
  onClear: () => void;
  onUndo: () => void;
}) {
  const isBoolean = field.kind === "boolean";
  const checked = truthy(value);
  return (
    <div className={`settings-field ${removed ? "settings-field-removed" : ""}`}>
      <div className="settings-field-main">
        <label className="settings-label" htmlFor={`env-${field.key}`}>
          {field.label}
          {field.restart ? <span className="settings-badge">restart</span> : null}
          {field.secret && !field.is_set ? (
            <span className="settings-badge settings-badge-default">not set</span>
          ) : field.source === "default" ? (
            field.default ? (
              <span className="settings-badge settings-badge-default">default</span>
            ) : (
              <span className="settings-badge settings-badge-default">optional</span>
            )
          ) : (
            <span className="settings-badge settings-badge-set">env</span>
          )}
          {field.secret && field.is_set ? (
            <span className="settings-badge settings-badge-set">set</span>
          ) : null}
        </label>
        <span className="settings-key">{field.key}</span>
        {field.description ? (
          <span className="settings-desc">{field.description}</span>
        ) : null}
        {field.default &&
        field.source !== "default" &&
        fieldBase(field) !== field.default ? (
          <span className="settings-default-hint">
            default:{" "}
            {field.kind === "boolean"
              ? truthy(field.default)
                ? "on"
                : "off"
              : field.default}
          </span>
        ) : null}
      </div>
      <div className="settings-control">
        {isBoolean ? (
          <button
            id={`env-${field.key}`}
            type="button"
            role="switch"
            aria-checked={checked}
            className={`settings-switch ${checked ? "settings-switch-on" : ""}`}
            onClick={() => onChange(checked ? "0" : "1")}
          >
            <span />
          </button>
        ) : field.kind === "select" && field.choices.length ? (
          <select
            id={`env-${field.key}`}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          >
            <option value="">(default)</option>
            {field.choices.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={`env-${field.key}`}
            type={field.secret ? "password" : field.kind === "number" ? "number" : "text"}
            value={value}
            placeholder={
              field.secret
                ? field.is_set
                  ? "Leave blank to keep current value"
                  : "Not set"
                : field.default
                  ? `(default: ${field.default})`
                  : "(not set)"
            }
            onChange={(event) => onChange(event.target.value)}
            spellCheck={false}
            autoComplete="off"
          />
        )}
        {removed ? (
          <button
            type="button"
            className="chip"
            onClick={onUndo}
            title="Undo removal"
          >
            undo
          </button>
        ) : (field.secret && field.is_set) || field.in_file ? (
          <button
            type="button"
            className="chip chip-bad"
            onClick={onClear}
            title="Remove this key from .env"
          >
            clear
          </button>
        ) : null}
      </div>
    </div>
  );
}
