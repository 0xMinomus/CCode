"""Agent runtime tuning: fast default effort, explicit stop rule, hidden fixed-level chip.

A new session started at the highest available reasoning level (`values.at(-1)`),
so every step of a simple request paid the slowest effort. The preferred level is
`low` when the model offers it, and the previous behaviour otherwise.

The selection completers read the level out of an optional member chain, so the
helper takes the level list itself: repeating the chain in a conditional would
introduce a second, unguarded reference to the minified receiver.

The composer's thinking-level chip is hidden while the level cannot be picked:
a model with a single, fixed level (its name already carries it, e.g.
`gemini-3.8-flash-high`) shows no chip at all, and a model that still offers a
choice keeps the chip and its label untouched.
"""

from . import replace_once

# Default effort inside the agent bundle, where the level list is a plain local.
AGENT_EFFORT = ('defaultLevel:s.values.at(-1)}',
                'defaultLevel:s.values.includes("low")?"low":s.values.at(-1)}')
HOST_SELECTION = ('let r=e.providers.find(o=>o.providerId===t.providerId)'
                  '?.models.find(o=>o.modelId===t.modelId)?.config.optionSpecs.reasoningLevel.values.at(-1);',
                  'let r=ccodePreferredReasoningLevel(e.providers.find(o=>o.providerId===t.providerId)'
                  '?.models.find(o=>o.modelId===t.modelId)?.config.optionSpecs.reasoningLevel.values);')
RENDERER_SELECTION = ('let n=(e.providers.find(e=>e.providerId===t.providerId)'
                      '?.models.find(e=>e.modelId===t.modelId))?.config.optionSpecs.reasoningLevel.values.at(-1);',
                      'let n=ccodePreferredReasoningLevel((e.providers.find(e=>e.providerId===t.providerId)'
                      '?.models.find(e=>e.modelId===t.modelId))?.config.optionSpecs.reasoningLevel.values);')
HELPER = '\nfunction ccodePreferredReasoningLevel(e){return e&&e.includes("low")?"low":e?.at(-1)}\n'

# `M` is the upstream flag for "single option, already selected": the level
# cannot be picked there, so the non-clickable chip is dropped entirely and the
# toolbar shows nothing for it. Models that still offer a choice keep their chip
# and label exactly as upstream.
CHIP_HIDDEN = ('return M?(0,$.jsx)(uA,{title:F,triggerRef:p,children:(0,$.jsx)(`span`,{className:Z('
               '`inline-flex h-7 items-center gap-1 rounded-lg px-1.5 py-1.5 text-ui-base text-foreground`,'
               'v,f),"aria-label":N,"data-thought-level-fixed":`true`,"data-composer-thought-control":'
               'n!==void 0||void 0,"data-composer-collapse-priority":n,"data-testid":Ba,children:V})})',
               'return M?null')
MARKERS = ('return M?null:r===`select`?',)

HARNESS_HEAD = ('return["# Harness","- Text you output outside of tool use is displayed to the user '
                'as Github-flavored markdown in a terminal.",')
HARNESS_TAIL = ('return["# Harness",'
                '"- Answer what was asked, then stop. A status or yes/no question takes one or two checks, '
                'not a plan, and never the same call twice with the same input.",'
                '"- One pass is enough: after a gate, test, or review passes, report and finish instead of '
                'running a second full pass over the same work.",'
                '"- Do not create Markdown files as a side effect of ordinary requests; create them only when the user explicitly asks or invokes a matching document slash command. Follow repository instructions that require documentation updates.",'
                '"- When a reviewer or gate tool fails to start, do the single equivalent check yourself once, '
                'then finish.",'
                '"- Text you output outside of tool use is displayed to the user as Github-flavored markdown '
                'in a terminal.",')


def patch_agent(text):
    text = replace_once(text, *AGENT_EFFORT)
    return replace_once(text, HARNESS_HEAD, HARNESS_TAIL)


def patch_renderer(text):
    """Hide the thinking chip while the model's level cannot be picked."""
    text = replace_once(text, *CHIP_HIDDEN)
    for marker in MARKERS:
        if marker not in text:
            raise ValueError('Reasoning chip patch marker is missing from the renderer bundle: ' + marker)
    return text


def patch_archive(archive, replacements, host, renderer):
    """Apply the effort default in the host and renderer selection completers."""
    for name, anchor in ((host, HOST_SELECTION), (renderer, RENDERER_SELECTION)):
        text = replace_once(replacements.get(name, archive.read(name)).decode(), *anchor)
        replacements[name] = (text + HELPER).encode()
    replacements[renderer] = patch_renderer(replacements[renderer].decode()).encode()
