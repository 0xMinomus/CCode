"""Build staging and renderer grouping for bundled default slash commands."""

import pathlib
import re
import shutil

from . import rebrand, replace_once

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / 'src/commands'
RESOURCE_DIR = 'commands'
RENDERER_ANCHOR = 'le.local.length>0?ge(le.local):me===0&&!a.trim()?'
COMMAND_NAME = re.compile(r'^[a-z0-9][a-z0-9-]*\.md$')


def source_files():
    files = sorted(SOURCE_DIR.iterdir())
    commands = [path for path in files if path.suffix == '.md']
    if not commands or any(path.is_symlink() or not path.is_file() or not COMMAND_NAME.fullmatch(path.name)
                           for path in commands):
        raise ValueError('Default command sources must be regular lowercase .md files')
    return commands


def resource_files():
    return [RESOURCE_DIR + '/main.cjs'] + [RESOURCE_DIR + '/defaults/' + path.name for path in source_files()]


def stage(output):
    destination = output / RESOURCE_DIR
    shutil.rmtree(destination, ignore_errors=True)
    defaults = destination / 'defaults'
    defaults.mkdir(parents=True)
    shutil.copy2(ROOT / 'src/main/commands.cjs', destination / 'main.cjs')
    for source in source_files():
        shutil.copy2(source, defaults / source.name)
    rebrand.rewrite_tree(destination)
    return resource_files()


def patch_renderer(text):
    return replace_once(text, RENDERER_ANCHOR,
                        'le.local.length>0?CCodeCommandCategoryList(le.local,ge):me===0&&!a.trim()?')

def patch_host(text):
    text = replace_once(
        text,
        'function Tve(e){let t=of(e);return un($w(),...t.userDirectorySegments)}',
        'function Tve(e){let t=of(e);return e==="ccodeAgent"?un(process.env.CCODE_STORAGE_DIR,"commands"):un($w(),...t.userDirectorySegments)}',
    )
    return replace_once(
        text,
        'function Bq(e){return un($w(),...e.userDirectorySegments)}',
        'function Bq(e){return e.agentSource==="ccodeAgent"?un(process.env.CCODE_STORAGE_DIR,"commands"):un($w(),...e.userDirectorySegments)}',
    )
