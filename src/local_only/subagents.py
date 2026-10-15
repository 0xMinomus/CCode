"""Version-pinned default subagent catalog and runtime wiring."""

import json

from . import replace_once


READ_ONLY_TOOLS = ("Glob", "Grep", "Read", "WebFetch", "WebSearch", "TodoWrite")
EXPLORER_TOOLS = ("Bash", "Glob", "Grep", "Read", "WebFetch", "WebSearch", "TodoWrite")
ALL_TOOLS = ("*",)

AGENTS = (
    {
        "name": "Engineering Generalist",
        "description": "Broad coding agent for cross-stack tasks and implementation.",
        "color": "blue",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": None,
    },
    {
        "name": "Codebase Explorer",
        "description": "Read-only codebase search and navigation.",
        "color": "cyan",
        "inject_agents_md": False,
        "tools": EXPLORER_TOOLS,
        "system_prompt": None,
    },
    {
        "name": "Technical Architect",
        "description": "Designs system boundaries and technical plans.",
        "color": "purple",
        "inject_agents_md": True,
        "tools": READ_ONLY_TOOLS,
        "system_prompt": (
            "You are the Technical Architect. Analyze the existing system and the requested outcome before proposing a design. "
            "Trace relevant components, contracts, and callers; prefer existing conventions and the smallest coherent design. "
            "Consider data flow, failure modes, performance, security, migrations, and rollback where relevant. "
            "Do not edit files or run mutating commands. Return a concrete plan with affected paths and interfaces, decisions, "
            "risks, and verification steps. Separate observed facts from assumptions."
        ),
    },
    {
        "name": "Backend Developer",
        "description": "Implements backend services, APIs, and business logic.",
        "color": "green",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the Backend Developer. Own server-side services, APIs, integrations, and business logic in the delegated scope. "
            "Inspect repository instructions and trace the full call path. Preserve data integrity, authorization checks, error semantics, "
            "and compatibility. Implement the smallest complete change, update relevant tests, and run targeted checks. "
            "Do not broaden scope, add retries, telemetry, or abstractions without a requirement. Do not commit, push, or deploy unless "
            "explicitly requested. Report changed paths and verification evidence."
        ),
    },
    {
        "name": "Frontend Developer",
        "description": "Builds accessible, responsive application interfaces.",
        "color": "orange",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the Frontend Developer. Implement the delegated interface behavior using existing components, design tokens, and "
            "project conventions. Preserve accessibility, keyboard behavior, responsive layout, and loading, empty, error, and disabled "
            "states. Keep changes scoped, update relevant tests, and inspect the actual rendered surface when practical. Do not claim visual "
            "verification from source inspection alone. Report changed paths and verification evidence."
        ),
    },
    {
        "name": "UI/UX Designer",
        "description": "Designs and implements clear, accessible interactions.",
        "color": "pink",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the UI/UX Designer. Study the requested surface, existing product language, components, and design tokens before "
            "changing it. Improve hierarchy, spacing, interaction clarity, accessibility, and edge states without changing unrelated behavior. "
            "Implement interface changes when directly delegated; otherwise return a concrete design specification for the Frontend Developer. "
            "Verify the rendered surface for visual work and report any limits."
        ),
    },
    {
        "name": "Database Engineer",
        "description": "Designs schemas, queries, and safe migrations.",
        "color": "yellow",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the Database Engineer. Own schema, query, indexing, and persistence changes in the delegated scope. Protect data "
            "integrity with appropriate constraints, transactions, and deterministic migrations. Preserve existing user data and define a "
            "rollback or recovery path for destructive changes. Test migration boundaries and query behavior with isolated data. Never copy "
            "secrets or live user data into source or test fixtures."
        ),
    },
    {
        "name": "Debugger & Performance Engineer",
        "description": "Finds root causes and removes bottlenecks.",
        "color": "red",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the Debugger and Performance Engineer. Reproduce the reported behavior before editing, trace every caller of the shared "
            "path, and identify the root cause rather than suppressing the symptom. Measure or inspect the relevant cost before optimizing. "
            "Make the smallest complete fix, add a regression check for the observed failure, and compare the result. State uncertainty and "
            "the evidence that resolves it."
        ),
    },
    {
        "name": "QA / Test Engineer",
        "description": "Validates acceptance behavior and regression coverage.",
        "color": "cyan",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the QA and Test Engineer. Convert the acceptance criteria into observable behavior checks. Cover boundaries, state "
            "transitions, error handling, and persistence with deterministic isolated tests. Prefer a test that fails for a plausible consumer "
            "bug over source-text assertions or mocks that only echo inputs. Do not modify production code unless the parent explicitly assigns "
            "implementation. Report commands run and their actual results."
        ),
    },
    {
        "name": "Code Reviewer",
        "description": "Reviews changes for correctness and maintainability.",
        "color": "blue",
        "inject_agents_md": True,
        "tools": READ_ONLY_TOOLS,
        "system_prompt": (
            "You are the Code Reviewer. Review the supplied diff and its callers without editing files. Prioritize concrete correctness, "
            "regression, data-loss, and maintainability findings. Report findings first, ordered by severity, with exact file and line evidence "
            "and the affected behavior. If no finding is supported, say so and note what you inspected; do not invent issues or rewrite the diff."
        ),
    },
    {
        "name": "Security Reviewer",
        "description": "Audits trust boundaries and attack paths.",
        "color": "red",
        "inject_agents_md": True,
        "tools": READ_ONLY_TOOLS,
        "system_prompt": (
            "You are the Security Reviewer. Inspect trust boundaries, authentication and authorization, input validation, secrets, filesystem "
            "and network access, and failure handling in the delegated scope. Do not edit files. Report only evidence-backed vulnerabilities, "
            "with severity, attacker capability, impact, reachable path, and a specific remediation. Distinguish confirmed issues from risks "
            "that need more evidence."
        ),
    },
    {
        "name": "DevOps Engineer",
        "description": "Owns builds, CI, packaging, and deployment configuration.",
        "color": "green",
        "inject_agents_md": True,
        "tools": ALL_TOOLS,
        "system_prompt": (
            "You are the DevOps Engineer. Own build, CI, packaging, runtime, and deployment configuration in the delegated scope. Preserve "
            "reproducibility, least privilege, secret handling, and rollback safety. Use existing scripts and pinned dependencies. Validate "
            "configuration with the project checks. Do not deploy to production, alter live services, or expose credentials unless the user "
            "explicitly authorizes that exact action."
        ),
    },
)

NAMES = tuple(agent["name"] for agent in AGENTS)
LEGACY_NAMES = {"general-purpose": "Engineering Generalist", "Explore": "Codebase Explorer"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _replace_region(text, start, end, replacement):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Subagent patch anchor changed: {start}")
    start_at = text.index(start)
    end_at = text.index(end, start_at + len(start))
    if end_at < 0:
        raise ValueError(f"Subagent patch boundary missing: {end}")
    return text[:start_at] + replacement + text[end_at:]


def _names_js(names=NAMES):
    return "[" + ",".join(_json(name) for name in names) + "]"


def _host_profile(agent):
    name = _json(agent["name"])
    return (
        "{id:cl({name:" + name + ',scope:"built-in",source:"built-in"}),name:' + name +
        ",description:" + _json(agent["description"]) +
        ",color:" + _json(agent["color"]) +
        ",injectAgentsMd:" + ("!0" if agent["inject_agents_md"] else "!1") +
        ",modelSelection:e[" + name + "],modelSelectionOverride:e[" + name + "]" +
        ',systemPrompt:' + _json(agent["system_prompt"] or "") +
        ",tools:" + _json(agent["tools"]) +
        ',path:"built-in:' + agent["name"] + '",scope:"built-in",source:"built-in",enabled:!0,readOnly:!0}'
    )


def _agent_profile(agent):
    name = _json(agent["name"])
    if agent["name"] == "Engineering Generalist":
        prompt = "Lvn()"
    elif agent["name"] == "Codebase Explorer":
        prompt = '""'
    else:
        prompt = _json(agent["system_prompt"])
    return (
        "{name:" + name +
        ",description:" + _json(agent["description"]) +
        ",color:" + _json(agent["color"]) +
        ",injectAgentsMd:" + ("!0" if agent["inject_agents_md"] else "!1") +
        ",...n[" + name + "]?{modelSelection:n[" + name + "]}:{}" +
        ',source:"built-in",systemPrompt:' + prompt +
        ",tools:" + _json(agent["tools"]) + ",enabled:!0}"
    )


def _host_override_loop():
    names = _names_js()[:-1] + ',"general-purpose","Explore"]'
    return (
        "for(let o of" + names + "){let s=t?wr.safeParse(Vl(e.builtInModelSelectionOverrides)[o]).data:"
        "pl({model:Vl(e.builtInModelOverrides)[o],thoughtLevel:Vl(e.builtInThoughtLevelOverrides)[o]});"
        'if(!s)continue;let a=!t&&s.providerId.startsWith("builtin:")?dc(s.providerId):s.providerId;'
        'let c=o==="general-purpose"?"Engineering Generalist":o==="Explore"?"Codebase Explorer":o;'
        "if(!Object.hasOwn(n,c))n[c]=a?{...s,providerId:a,modelId:t?s.modelId:cc(s.providerId,s.modelId)}:s}"
    )


def _agent_override_loop():
    names = _names_js()[:-1] + ',"general-purpose","Explore"]'
    return (
        "for(let s of" + names + "){let a=t?Pu.safeParse(tAe(e.builtInModelSelectionOverrides)[s]).data:"
        "uee({model:tAe(e.builtInModelOverrides)[s],thoughtLevel:tAe(e.builtInThoughtLevelOverrides)[s]});"
        "if(!a)continue;let c=s==="
        '"general-purpose"?"Engineering Generalist":s==="Explore"?"Codebase Explorer":s;'
        "if(Object.hasOwn(n,c))continue;"
        'let l=!t&&a.providerId.startsWith("builtin:")?yz(a.providerId):a.providerId;'
        "n[c]=l?{...a,providerId:l,modelId:t?a.modelId:lee(a.providerId,a.modelId)}:a}"
    )


def _host_selection_normalizer():
    names = _names_js()[:-1] + ',"general-purpose","Explore"]'
    return (
        "function mve(e){let t={},n=Id(e)?e:{};for(let r of" + names + "){"
        'let o=wr.safeParse(n[r]).data;if(!o)continue;'
        'let s=r==="general-purpose"?"Engineering Generalist":r==="Explore"?"Codebase Explorer":r;'
        "if(!Object.hasOwn(t,s))t[s]=o}return t}"
    )


def _agent_selection_normalizer():
    names = _names_js()[:-1] + ',"general-purpose","Explore"]'
    return (
        "function bHa(e){let t={},n=_Ha(e)?e:{};for(let o of" + names + "){"
        "let s=Pu.safeParse(n[o]);if(!s.success)continue;"
        'let a=o==="general-purpose"?"Engineering Generalist":o==="Explore"?"Codebase Explorer":o;'
        "if(!Object.hasOwn(t,a))t[a]=s.data}return t}"
    )


def patch_renderer(text):
    text = replace_once(
        text,
        "function iTn(e){return O7(e)&&e.scope===`user`}",
        "function iTn(e){return aTn(e)||O7(e)&&e.scope===`user`}",
    )
    name_checks = "||".join(f'e.name==={_json(name)}' for name in NAMES)
    return replace_once(
        text,
        "function sTn(e){return aTn(e)&&(e.name===`general-purpose`||e.name===`Explore`)?e.name:null}",
        f"function sTn(e){{return aTn(e)&&({name_checks})?e.name:null}}",
    )


def patch_host(text):
    text = replace_once(
        text,
        'Sq=new Set(["general-purpose","Explore"])',
        "Sq=new Set(" + _names_js() + ")",
    )
    text = _replace_region(
        text,
        "function tve(e={}){",
        'i(tve,"createBuiltInAgents")',
        "function tve(e={}){return[" + ",".join(_host_profile(agent) for agent in AGENTS) + "]}",
    )
    text = replace_once(
        text,
        'for(let o of["Explore","general-purpose"]){let s=t?wr.safeParse(Vl(e.builtInModelSelectionOverrides)[o]).data:pl({model:Vl(e.builtInModelOverrides)[o],thoughtLevel:Vl(e.builtInThoughtLevelOverrides)[o]});if(!s)continue;let a=!t&&s.providerId.startsWith("builtin:")?dc(s.providerId):s.providerId;n[o]=a?{...s,providerId:a,modelId:t?s.modelId:cc(s.providerId,s.modelId)}:s}',
        _host_override_loop(),
    )
    text = _replace_region(
        text,
        "function mve(e){",
        'i(mve,"normalizeBuiltInSelectionOverrides")',
        _host_selection_normalizer(),
    )
    return replace_once(
        text,
        'enabled:r.scope==="user"?!n.has(r.id):!0',
        'enabled:r.source==="built-in"||r.scope==="user"?!n.has(r.id):!0',
    )


def patch_agent(text):
    text = replace_once(
        text,
        'You are an agent for CCode CLI.',
        'You are the Engineering Generalist for CCode CLI.',
    )
    text = replace_once(
        text,
        'r(Lvn,"buildGeneralPurposeSystemPrompt")',
        'r(Lvn,"buildEngineeringGeneralistSystemPrompt")',
    )
    text = replace_once(
        text,
        'You are CCode Explore, a file search and codebase research specialist for CCode CLI. You excel at thoroughly navigating and exploring codebases.',
        'You are the Codebase Explorer for CCode CLI, a read-only file search and codebase research specialist. You locate relevant code by navigating directories and reading focused excerpts.',
    )
    text = replace_once(
        text,
        'r(jvn,"buildExploreAgentPrompt")',
        'r(jvn,"buildCodebaseExplorerPrompt")',
    )
    text = replace_once(text, 'Nvn="general-purpose"', 'Nvn="Engineering Generalist"')
    text = replace_once(text, 'R$="Explore"', 'R$="Codebase Explorer"')
    text = replace_once(
        text,
        'gvr={GeneralPurpose:"general-purpose",Explore:"Explore"}',
        'gvr={EngineeringGeneralist:"Engineering Generalist",CodebaseExplorer:"Codebase Explorer"}',
    )
    text = replace_once(text, 'gvr.GeneralPurpose', 'gvr.EngineeringGeneralist')
    text = replace_once(
        text,
        'If omitted, the general-purpose agent is used.',
        'If omitted, the Engineering Generalist is used.',
    )
    text = replace_once(
        text,
        'r(fpa,"createBuiltInExploreAgentProfile")',
        'r(fpa,"createBuiltInCodebaseExplorerProfile")',
    )
    text = replace_once(
        text,
        'r(vFe,"isBuiltInExploreAgentProfile")',
        'r(vFe,"isBuiltInCodebaseExplorerProfile")',
    )
    text = replace_once(
        text,
        'r(mpa,"createBuiltInGeneralPurposeAgentProfile")',
        'r(mpa,"createEngineeringGeneralistProfile")',
    )
    text = replace_once(
        text,
        'function dtr(e){let t=Object.hasOwn(e,"builtInModelSelectionOverrides"),n={};for(let s of["Explore","general-purpose"]){let a=t?Pu.safeParse(tAe(e.builtInModelSelectionOverrides)[s]).data:uee({model:tAe(e.builtInModelOverrides)[s],thoughtLevel:tAe(e.builtInThoughtLevelOverrides)[s]});if(!a)continue;let l=!t&&a.providerId.startsWith("builtin:")?yz(a.providerId):a.providerId;n[s]=l?{...a,providerId:l,modelId:t?a.modelId:lee(a.providerId,a.modelId)}:a}let o=Object.hasOwn(e,"pluginAgentModelSelectionOverrides")?eAe(e.pluginAgentModelSelectionOverrides):Object.fromEntries(Object.entries(tAe(e.pluginAgentModelOverrides)).flatMap(([s,a])=>{let l=uee({model:a,thoughtLevel:tAe(e.pluginAgentThoughtLevelOverrides)[s]});if(!s.startsWith("plugin:")||!l)return[];let u=l.providerId.startsWith("builtin:")?yz(l.providerId):l.providerId;return[[s,u?{...l,providerId:u,modelId:lee(l.providerId,l.modelId)}:l]]}));return{...e,builtInModelSelectionOverrides:n,pluginAgentModelSelectionOverrides:o}}',
        'function dtr(e){let t=Object.hasOwn(e,"builtInModelSelectionOverrides"),n={};'
        + _agent_override_loop()
        + 'let o=Object.hasOwn(e,"pluginAgentModelSelectionOverrides")?eAe(e.pluginAgentModelSelectionOverrides):Object.fromEntries(Object.entries(tAe(e.pluginAgentModelOverrides)).flatMap(([s,a])=>{let l=uee({model:a,thoughtLevel:tAe(e.pluginAgentThoughtLevelOverrides)[s]});if(!s.startsWith("plugin:")||!l)return[];let u=l.providerId.startsWith("builtin:")?yz(l.providerId):l.providerId;return[[s,u?{...l,providerId:u,modelId:lee(l.providerId,l.modelId)}:l]]}));return{...e,builtInModelSelectionOverrides:n,pluginAgentModelSelectionOverrides:o}}',
    )
    text = replace_once(
        text,
        'fHa=new Set(["general-purpose","Explore"])',
        'fHa=new Set(' + _names_js() + ')',
    )
    text = _replace_region(
        text,
        "function bHa(e){",
        "function SHa(e,t){",
        _agent_selection_normalizer(),
    )
    profile_block = (
        "function fpa(e={}){return{name:R$,description:" + _json(AGENTS[1]["description"]) +
        ',color:"cyan",injectAgentsMd:!1,...e.modelSelection?{modelSelection:e.modelSelection}:{},source:"built-in",systemPrompt:"",tools:' +
        _json(EXPLORER_TOOLS) +
        ',enabled:!0}}function vFe(e){return e.name===R$&&e.source==="built-in"}'
        "function $vn(e,t={}){let n=t.builtInModelSelectionOverrides??{},o=new Map;"
        "o.set(jht,mpa({modelSelection:n[jht]})),o.set(R$,fpa({modelSelection:n[R$]}));"
        "for(let s of[" + ",".join(_agent_profile(agent) for agent in AGENTS[2:]) + "])o.set(s.name,s);"
        "for(let s of e)o.set(s.name,s);let a=new Set(t.disabledAgentIds??[]);"
        'return Array.from(o.values()).filter(s=>s.enabled!==!1&&(s.source!=="built-in"||!a.has(`built-in:built-in:${s.name.trim().toLowerCase()}`)))}'
        "function mpa(e={}){return{name:jht,description:" + _json(AGENTS[0]["description"]) +
        ',color:"blue",injectAgentsMd:!0,...e.modelSelection?{modelSelection:e.modelSelection}:{},source:"built-in",systemPrompt:Lvn(),tools:["*"],enabled:!0}}'
    )
    text = _replace_region(text, "function fpa(e={})", "function bho(e,t={})", profile_block)
    text = replace_once(
        text,
        'function bho(e,t={}){let n=$vn(e);',
        'function bho(e,t={}){let n=$vn(e,t);',
    )
    text = replace_once(
        text,
        'bho(e.profiles??[],{embeddedSearchEnabled:e.embeddedSearchEnabled})',
        'bho(e.profiles??[],{embeddedSearchEnabled:e.embeddedSearchEnabled,disabledAgentIds:e.disabledAgentIds})',
    )
    text = replace_once(
        text,
        'Wvn({embeddedSearchEnabled:t.embeddedSearchEnabled,profiles:t.agentProfiles,dynamicWorkflowEnabled:t.includeDynamicWorkflow!==!1})',
        'Wvn({embeddedSearchEnabled:t.embeddedSearchEnabled,profiles:t.agentProfiles,disabledAgentIds:t.disabledAgentIds,dynamicWorkflowEnabled:t.includeDynamicWorkflow!==!1})',
    )
    text = text.replace(
        'agentProfiles:e.config.subagents?.profiles,allowedTools:',
        'agentProfiles:e.config.subagents?.profiles,disabledAgentIds:e.config.subagents?.disabledAgentIds,allowedTools:',
    )
    if text.count('disabledAgentIds:e.config.subagents?.disabledAgentIds,allowedTools:') != 2:
        raise ValueError("Subagent tool wiring anchor changed: agentProfiles")
    text = replace_once(
        text,
        'agentProfiles:this.config.subagents?.profiles,embeddedSearchEnabled:',
        'agentProfiles:this.config.subagents?.profiles,disabledAgentIds:this.config.subagents?.disabledAgentIds,embeddedSearchEnabled:',
    )
    text = replace_once(
        text,
        'pluginAgentModelSelectionOverrides:s.pluginAgentModelSelectionOverrides,diagnostics:o,profiles:a}',
        'pluginAgentModelSelectionOverrides:s.pluginAgentModelSelectionOverrides,disabledAgentIds:[...s.disabledAgentIds],diagnostics:o,profiles:a}',
    )
    text = replace_once(
        text,
        'profiles:[...o.runtimeConfig?.subagents?.profiles??[],...g]},memory:',
        'profiles:[...o.runtimeConfig?.subagents?.profiles??[],...g],disabledAgentIds:e.disabledAgentIds??[]},memory:',
    )
    text = replace_once(
        text,
        'builtInSubagentModelSelectionOverrides:U.builtInModelSelectionOverrides,subagentOutputRootDir:',
        'builtInSubagentModelSelectionOverrides:U.builtInModelSelectionOverrides,disabledAgentIds:U.disabledAgentIds,subagentOutputRootDir:',
    )
    text = replace_once(
        text,
        'profiles:this.config.subagents?.profiles,builtInModelSelectionOverrides:this.config.subagents?.builtInModelSelectionOverrides,runtimeTaskRegistry:',
        'profiles:this.config.subagents?.profiles,builtInModelSelectionOverrides:this.config.subagents?.builtInModelSelectionOverrides,disabledAgentIds:this.config.subagents?.disabledAgentIds,runtimeTaskRegistry:',
    )
    text = replace_once(
        text,
        's=$vn(e.profiles??[],{builtInModelSelectionOverrides:e.builtInModelSelectionOverrides})',
        's=$vn(e.profiles??[],{builtInModelSelectionOverrides:e.builtInModelSelectionOverrides,disabledAgentIds:e.disabledAgentIds})',
    )
    for old, new in (
        ('Explore subagent spawned', 'Subagent spawned'),
        ('Explore subagent completed', 'Subagent completed'),
        ('Explore subagent failed', 'Subagent failed'),
        ('Explore subagent background task started', 'Subagent background task started'),
        ('Explore subagent activity watchdog fired', 'Subagent activity watchdog fired'),
    ):
        text = replace_once(text, old, new)
    return text
