// Reuse General Settings row and switch; no separate visual language or motion.
function CCodeStartupPrewarm() {
  const [state, setState] = Q.useState(null);
  const [error, setError] = Q.useState("");
  const [busy, setBusy] = Q.useState(false);
  Q.useEffect(() => {
    let active = true;
    const api = window.ccodeStartupPrewarm;
    if (!api) { setError("Startup settings are unavailable in this window."); return; }
    api.get().then(value => { if (active) { setState(value); setError(value.error || ""); } })
      .catch(() => { if (active) setError("Could not load startup settings."); });
    return () => { active = false; };
  }, []);
  const save = async enabled => {
    if (busy) return;
    setBusy(true);
    try {
      const value = await window.ccodeStartupPrewarm.set(enabled);
      setState(value); setError(value.error || "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message.replace(/^Error invoking remote method '[^']+': Error: /, "") : "Could not save startup settings.");
    } finally { setBusy(false); }
  };
  return $.jsx(Z1, {
    label: "Start CCode in the background at login",
    description: $.jsxs("div", { children: [
      "Start CCode hidden when you sign in, so your workspace is ready when you open it.",
      error ? $.jsx("div", { role: "alert", className: "mt-1 text-ui-sm text-foreground-subtle", children: error }) : null
    ] }),
    control: $.jsx(Xx, { "aria-label": "Start CCode in the background at login", checked: state?.enabled ?? false,
      disabled: busy || !state?.supported, onCheckedChange: save })
  });
}
