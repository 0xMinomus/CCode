"""Agent runtime tuning: fast default effort, explicit stop rule.

A new session started at the highest available reasoning level (`values.at(-1)`),
so every step of a simple request paid the slowest effort. The preferred level is
`low` when the model offers it, and the previous behaviour otherwise.

The selection completers read the level out of an optional member chain, so the
helper takes the level list itself: repeating the chain in a conditional would
introduce a second, unguarded reference to the minified receiver.
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


def patch_archive(archive, replacements, host, renderer):
    """Apply the effort default in the host and renderer selection completers."""
    for name, anchor in ((host, HOST_SELECTION), (renderer, RENDERER_SELECTION)):
        text = replace_once(replacements.get(name, archive.read(name)).decode(), *anchor)
        replacements[name] = (text + HELPER).encode()
