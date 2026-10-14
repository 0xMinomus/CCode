"""Agent runtime tuning: fast default effort, explicit stop rule.

A new session started at the highest available reasoning level (`values.at(-1)`),
so every step of a simple request paid the slowest effort. The preferred level is
`low` when the model offers it, and the previous behaviour otherwise. The Harness
lines give the model an explicit stopping rule, which is what keeps a status
question from turning into a chain of re-checks.
"""

from . import replace_once

# Default effort for a new session: the cheapest productive level the model offers.
AGENT_EFFORT = ('defaultLevel:s.values.at(-1)}',
                'defaultLevel:s.values.includes("low")?"low":s.values.at(-1)}')
# Same default when the host or the renderer completes a model selection.
SELECTION_EFFORT = ('optionSpecs.reasoningLevel.values.at(-1)',
                    'optionSpecs.reasoningLevel.values.includes("low")?"low":optionSpecs.reasoningLevel.values.at(-1)')
HARNESS_HEAD = ('return["# Harness","- Text you output outside of tool use is displayed to the user '
                'as Github-flavored markdown in a terminal.",')
HARNESS_TAIL = ('return["# Harness",'
                '"- Answer what was asked, then stop. A status or yes/no question takes one or two checks, '
                'not a plan, and never the same call twice with the same input.",'
                '"- One pass is enough: after a gate, test, or review passes, report and finish instead of '
                'running a second full pass over the same work.",'
                '"- When a reviewer or gate tool fails to start, do the single equivalent check yourself once, '
                'then finish.",'
                '"- Text you output outside of tool use is displayed to the user as Github-flavored markdown '
                'in a terminal.",')


def patch_agent(text):
    text = replace_once(text, *AGENT_EFFORT)
    return replace_once(text, HARNESS_HEAD, HARNESS_TAIL)


def patch_archive(archive, replacements, assets):
    """Apply the effort default wherever a model selection is completed."""
    for name in assets:
        text = replacements.get(name, archive.read(name)).decode()
        replacements[name] = replace_once(text, *SELECTION_EFFORT).encode()
