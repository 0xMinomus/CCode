"""Build staging and renderer grouping for bundled default slash commands."""

import pathlib
import re
import shutil

from . import rebrand, replace_once

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / 'src/commands'
RESOURCE_DIR = 'commands'
RENDERER_ANCHOR = 'le.local.length>0?ge(le.local):me===0&&!a.trim()?'
SLASH_PICKER_ANCHOR = ('function _9e({workspacePath:e,workspaceIdentity:t,sessionId:n,provider:r,container:i,disabled:a=!1,excludedCommandNames:o,appCommands:s})'
                       '{let[c]=TL(),{intl:l,locale:u}=q()')
SLASH_PICKER_REPLACEMENT = ('function _9e({workspacePath:e,workspaceIdentity:t,sessionId:n,provider:r,container:i,disabled:a=!1,excludedCommandNames:o,appCommands:s})'
                            '{let[c]=TL(),ccodeCommandsService=Dg().commandsService,'
                            '[ccodeCommands,setCcodeCommands]=(0,Q.useState)(()=>[]),{intl:l,locale:u}=q()')
SLASH_COMMAND_STATE_ANCHOR = 'p=oR(e,t),'
SLASH_COMMAND_STATE_REPLACEMENT = 'p=CCodeMergeSlashCommands(oR(e,t),ccodeCommands),'
SLASH_PICKER_EFFECT_ANCHOR = '(0,Q.useEffect)(()=>{C.current=M},[M]),'
SLASH_PICKER_EFFECT_REPLACEMENT = (
    '(0,Q.useEffect)(()=>{let n=!0,r=e??null,i=t??null,a=U2.subscribe(e=>{'
    'e.workspacePath===r&&e.workspaceIdentity===i&&setCcodeCommands(e.commands)});'
    'if(ccodeCommandsService)void R5t({commandsService:ccodeCommandsService,reason:"composer-startup",'
    'workspacePath:e??null,workspaceIdentity:t??null}).then(e=>{n&&Array.isArray(e)&&setCcodeCommands(e)});'
    'return()=>{n=!1,a()}},[ccodeCommandsService,e,t]),'
    '(0,Q.useEffect)(()=>{C.current=M},[M]),'
)
SLASH_COMMAND_MERGE_ANCHOR = ('let o=lo.getState(),s=o.getWorkspaceState(r,a).slashCommands;'
                             'o.setSlashCommands(r,F5t(s,e.commands),a)')
SLASH_COMMAND_MERGE_REPLACEMENT = ('let o=lo.getState(),s=o.getWorkspaceState(r,a).slashCommands;'
                                   'o.setSlashCommands(r,F5t(s,e.commands),a);return e.commands')
SLASH_REFRESH_FAILURE_ANCHOR = '[plugins] refresh slash commands after remote plugin sync failed'
SLASH_REFRESH_FAILURE_REPLACEMENT = '[commands] refresh slash commands failed'
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
    text = replace_once(text, RENDERER_ANCHOR,
                        'le.local.length>0?CCodeCommandCategoryList(le.local,ge):me===0&&!a.trim()?')
    text = replace_once(text, SLASH_PICKER_ANCHOR, SLASH_PICKER_REPLACEMENT)
    text = replace_once(text, SLASH_COMMAND_STATE_ANCHOR, SLASH_COMMAND_STATE_REPLACEMENT)
    text = replace_once(text, SLASH_PICKER_EFFECT_ANCHOR, SLASH_PICKER_EFFECT_REPLACEMENT)
    text = replace_once(text, SLASH_COMMAND_MERGE_ANCHOR, SLASH_COMMAND_MERGE_REPLACEMENT)
    return replace_once(text, SLASH_REFRESH_FAILURE_ANCHOR, SLASH_REFRESH_FAILURE_REPLACEMENT)

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
