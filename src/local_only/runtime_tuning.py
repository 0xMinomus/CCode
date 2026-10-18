"""Agent runtime tuning: fast default effort, explicit stop rule, honest chip.

A new session started at the highest available reasoning level (`values.at(-1)`),
so every step of a simple request paid the slowest effort. The preferred level is
`low` when the model offers it, and the previous behaviour otherwise.

The selection completers read the level out of an optional member chain, so the
helper takes the level list itself: repeating the chain in a conditional would
introduce a second, unguarded reference to the minified receiver.

The composer's thinking-level chip keeps its label only while the level is
actually selectable. A model with a single, fixed level (its name already carries
it, e.g. `gemini-3.8-flash-high`) is not clickable, so that branch renders the
brain icon alone and dims to `text-foreground-subtle`.
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

# The chip's label span is shared by the clickable branches; `M` is the upstream
# flag for "single option, already selected" (the non-clickable branch).
CHIP_LABEL = ('(0,$.jsx)(`span`,{ref:y,className:Z(`min-w-0 whitespace-nowrap`,o,n!==void 0'
              '&&`group-data-[composer-compact]/thought:hidden`),children:(0,$.jsx)(VH,{label:N})})',
              'M?null:(0,$.jsx)(`span`,{ref:y,className:Z(`min-w-0 whitespace-nowrap`,o,n!==void 0'
              '&&`group-data-[composer-compact]/thought:hidden`),children:(0,$.jsx)(VH,{label:N})})')
CHIP_FIXED = ('children:(0,$.jsx)(`span`,{className:Z(`inline-flex h-7 items-center gap-1 rounded-lg '
              'px-1.5 py-1.5 text-ui-base text-foreground`,v,f),"aria-label":N,"data-thought-level-fixed":`true`,',
              'children:(0,$.jsx)(`span`,{className:Z(`inline-flex h-7 items-center gap-1 rounded-lg '
              'px-1.5 py-1.5 text-ui-base text-foreground-subtle`,v,f),"aria-label":N,"data-thought-level-fixed":`true`,')
MARKERS = ('M?null:(0,$.jsx)(`span`,{ref:y,',
           'text-ui-base text-foreground-subtle`,v,f),"aria-label":N,"data-thought-level-fixed":`true`')

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
    """Icon-only, dimmed chip for a model whose thinking level cannot be picked."""
    text = replace_once(text, *CHIP_LABEL)
    text = replace_once(text, *CHIP_FIXED)
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
