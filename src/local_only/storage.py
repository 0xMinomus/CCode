"""Standalone storage boundaries for the pinned ZCode 3.14.5 bundles."""

from . import replace_once


_ENV_BODY = '''const zcodeStandaloneRoot=zcodeStandalonePath.resolve(process.env.ZCODE_STANDALONE_ROOT?.trim()||zcodeStandalonePath.join(zcodeStandaloneOs.homedir(),".local","share","ccode"));
const zcodeStandaloneData=zcodeStandalonePath.join(zcodeStandaloneRoot,"data");
Object.assign(process.env,{ZCODE_STANDALONE_ROOT:zcodeStandaloneRoot,ZCODE_DATA_BASE_DIR:zcodeStandaloneData,ZCODE_DESKTOP_HOME_DIR:zcodeStandaloneData,DESKTOP_HOME_DIR:zcodeStandaloneData,ZCODE_STORAGE_DIR:zcodeStandalonePath.join(zcodeStandaloneData,".zcode"),STORAGE_DIR:zcodeStandalonePath.join(zcodeStandaloneData,".zcode"),ZCODE_SESSION_DB_PATH:zcodeStandalonePath.join(zcodeStandaloneData,".zcode","cli","db","db.sqlite"),ZCODE_DESKTOP_USER_DATA_DIR:zcodeStandalonePath.join(zcodeStandaloneRoot,"electron"),ZCODE_DESKTOP_SESSION_DATA_DIR:zcodeStandalonePath.join(zcodeStandaloneRoot,"electron","session"),ZCODE_DESKTOP_USE_ELECTRON_DEFAULT_USER_DATA:"0",ZCODE_DESKTOP_APPLICATION_NAME:"ccode"});
'''
ESM_BOOTSTRAP = 'import * as zcodeStandaloneOs from "node:os";import * as zcodeStandalonePath from "node:path";\n' + _ENV_BODY
AGENT_BOOTSTRAP = 'const zcodeStandaloneOs=require("node:os"),zcodeStandalonePath=require("node:path");\n' + _ENV_BODY
_ERROR = 'throw new Error("Standalone storage root cannot be changed in settings; set ZCODE_STANDALONE_ROOT before launch")'


def _patch(archive, replacements, name, edits):
    text = replacements[name].decode() if name in replacements else archive.read(name).decode()
    for old, new in edits:
        text = replace_once(text, old, new)
    replacements[name] = text.encode()


def patch_archive(archive, replacements, renderer_asset):
    # Leaf runtime imports execute before any consumer captures its storage paths.
    for name, anchor in (
        ('out/main/chunk-HH7N2YVI.js', 'var i=Object.create;'),
        ('out/host/chunk-IYVG6UP7.js', 'var z=Object.create;'),
        ('out/scheduler/chunk-F6SSJBPP.js', 'var '),
    ):
        text = replacements[name].decode() if name in replacements else archive.read(name).decode()
        first = text[:text.index(';') + 1] if anchor == 'var ' else anchor
        replacements[name] = replace_once(text, first, ESM_BOOTSTRAP + first).encode()

    _patch(archive, replacements, 'out/main/chunk-BTD2TF4G.js', [
        ('function Zu(e){eo=e?.trim()||null}', 'function Zu(e){if(e?.trim()&&e.trim()!==fs){' + _ERROR + '}eo=fs}'),
        ('function de(){return eo||fs||$u}', 'function de(){return fs}'),
        ('function of(){let e=process.env.ZCODE_DESKTOP_HOME_DIR?.trim()||process.env.HOME?.trim()||process.env.USERPROFILE?.trim();return e&&e.length>0?e:$s()}', 'function of(){return de()}'),
        ('function Cn(){return St.parse({})}', 'function Cn(){return St.parse({dataBaseDir:de()})}'),
        ('let o=St.safeParse(uo(n));', 'let o=St.safeParse({...uo(n),dataBaseDir:de()});'),
        ('async update(f,g){await a(', 'async update(f,g){if(Object.hasOwn(f,"dataBaseDir")){if(f.dataBaseDir?.trim()&&f.dataBaseDir.trim()!==de()){' + _ERROR + '}f={...f,dataBaseDir:de()}}await a('),
        ('async updateDataBaseDir(f){let g=de(),h=f?.trim()||$s(),y=no(h);if(!y.ok){let P=new Error(`${y.code}: ${y.forbiddenDir}`);throw P.code=y.code,P}g!==h&&(Pe("copying data directory from",g,"to",h),await io(g,h),Pe("data directory copy done")),await this.update({dataBaseDir:f})}', 'async updateDataBaseDir(f){if(f?.trim()&&f.trim()!==de()){' + _ERROR + '}await this.update({dataBaseDir:de()})}'),
    ])
    _patch(archive, replacements, 'out/host/chunk-IKTGKLU2.js', [
        ('function Te(){return Tr||yr||zn}', 'function Te(){return yr}'),
    ])
    _patch(archive, replacements, 'out/scheduler/index.js', [
        ('function Ft(){return cT||dT||yH}', 'function Ft(){return dT}'),
    ])
    _patch(archive, replacements, 'out/main/index.js', [
        ('function AI(e=EI()){return TI(e,".zcode","v2","setting.json")}', 'function AI(e=ro()){return TI(e,".zcode","v2","setting.json")}'),
        ('function bf(){let e=xI();return e&&ks(e),e}', 'function bf(){let e=ro();return ks(e),e}'),
        ('function LI(e=OI()){return WI(e,".zcode","v2","setting.json")}', 'function LI(e=ro()){return WI(e,".zcode","v2","setting.json")}'),
        ('Z.setName(vr);$c&&Z.setPath("home",$c);', 'Z.setName(vr);'),
        ('let o=t==="user"?yH():r;', 'let o=t==="user"?ro():r;'),
        ('async function rk(e,t){let r=await Pu(zr,e,t);return r.length>0?r:Pu(ok,e,t)}', 'async function rk(e,t){let r=await Pu(zr,e,t);return e==="user"||r.length>0?r:Pu(ok,e,t)}'),
        ('async function rs(e){for(let t of mH(e))if(t.endsWith("store.json")){let r=await lH(t);if(r)return r}else{let r=await pH(t);if(r)return r}return{servers:{},totalCount:0,importedCount:0,skippedCount:0}}', 'async function rs(e){throw new Error("Legacy Common MCP migration is unavailable in the standalone application")}'),
        ('function gv(){return qe(mv(),".zcode","cli")}', 'function gv(){return qe(ro(),".zcode","cli")}'),
        ('function wv(){return qe(mv(),".zcode","computer-use","run")}', 'function wv(){return qe(ro(),".zcode","computer-use","run")}'),
    ])
    _patch(archive, replacements, 'out/host/index.js', [
        ('function z9(){let e=process.env.ZCODE_DESKTOP_HOME_DIR?.trim()||process.env.HOME?.trim()||process.env.USERPROFILE?.trim();return e&&e.length>0?e:nB()}', 'function z9(){return Ai()}'),
        ('function qg(){return il.parse({})}', 'function qg(){return il.parse({dataBaseDir:Ai()})}'),
        ('async update(d,l){', 'async update(d,l){if(Object.hasOwn(d,"dataBaseDir")){if(d.dataBaseDir?.trim()&&d.dataBaseDir.trim()!==Ai()){' + _ERROR + '}d={...d,dataBaseDir:Ai()}}'),
        ('async updateDataBaseDir(d){let l=Ai(),u=d?.trim()||nB(),p=$S(u);if(!p.ok){let f=new Error(`${p.code}: ${p.forbiddenDir}`);throw f.code=p.code,f}l!==u&&(Qo("copying data directory from",l,"to",u),await qS(l,u),Qo("data directory copy done")),await this.update({dataBaseDir:d})}', 'async updateDataBaseDir(d){if(d?.trim()&&d.trim()!==Ai()){' + _ERROR + '}await this.update({dataBaseDir:Ai()})}'),
        ('let r=t==="user"?jp():n;', 'let r=t==="user"?Ai():n;'),
        ('async function fR(){let e=await h1(ui);return e.length>0?m1(e):m1(await h1(hR))}', 'async function fR(){return m1(await h1(ui))}'),
        ('async function g1(e,t){let n=await mR(ui,e,t);return n.length>0?n:mR(hR,e,t)}', 'async function g1(e,t){let n=await mR(ui,e,t);return e==="user"||n.length>0?n:mR(hR,e,t)}'),
        ('function c1(){return process.env.HOME?.trim()||process.env.USERPROFILE?.trim()||qhe()}', 'function c1(){return Ai()}'),
        ('function aA(){let e=process.env.HOME?.trim()||process.env.USERPROFILE?.trim();return e&&e.length>0?e:DSe()}', 'function aA(){return Ai()}'),
        ('function rhe(e){let t=li(e.storage)?e.storage:{};return typeof t.dir=="string"&&t.dir.trim().length>0?t.dir:"~/.zcode"}', 'function rhe(e){return process.env.ZCODE_STORAGE_DIR}'),
        ('function Lw(e){let t=await Kwe(e),n=lq(t.storage)?t.storage:{},r=typeof n.dir=="string"&&n.dir.trim().length>0?n.dir.trim():"~/.zcode";return jwe(r,e)}', 'function Lw(e){return process.env.ZCODE_STORAGE_DIR}'),
        ('...t.readLegacyProviders?{importLegacy:i(async()=>qI({legacyProviders:await t.readLegacyProviders()}),"importLegacy")}:{}};', '};'),
    ])


def patch_agent(text):
    head = '#!/usr/bin/env node\n"use strict";'
    if text.count(head) != 1:
        raise ValueError(f'Agent bundle head changed ({text.count(head)} matches)')
    text = text.replace(head, head + '\n' + AGENT_BOOTSTRAP, 1)
    edits = [
        ('tHr="~/.zcode/cli"', 'tHr=zcodeStandalonePath.join(zcodeStandaloneData,".zcode","cli")'),
        ('function MQt(){return(0,ott.join)((0,Lwr.homedir)(),".zcode","cli","db","db.sqlite")}', 'function MQt(){return process.env.ZCODE_SESSION_DB_PATH}'),
        ('storage:{dir:"~/.zcode",sessionDbPath:"~/.zcode/cli/db/db.sqlite"}', 'storage:{dir:process.env.ZCODE_STORAGE_DIR,sessionDbPath:process.env.ZCODE_SESSION_DB_PATH}'),
        ('storage:{dir:this.store.get(fs.StorageDir)??Lm.storage.dir,sessionDbPath:this.store.get(fs.StorageSessionDbPath)??Lm.storage.sessionDbPath}', 'storage:{dir:process.env.ZCODE_STORAGE_DIR,sessionDbPath:process.env.ZCODE_SESSION_DB_PATH}'),
        ('function N6s(){return(0,mat.join)((0,HVr.homedir)(),".zcode","cli","log")}', 'function N6s(){return(0,mat.join)(process.env.ZCODE_STORAGE_DIR,"cli","log")}'),
        ('function e4s(e){return(0,cOe.join)((0,WWr.homedir)(),".zcode","cli",e?"debug":"rollout")}', 'function e4s(e){return(0,cOe.join)(process.env.ZCODE_STORAGE_DIR,"cli",e?"debug":"rollout")}'),
        ('function Sls(e){let t=e.HOME?.trim()||e.USERPROFILE?.trim();return t&&t.length>0?t:(0,vme.homedir)()}', 'function Sls(e){return zcodeStandaloneData}'),
        ('a=t.homeDirectory??(0,bun.homedir)()', 'a=t.homeDirectory??zcodeStandaloneData'),
        ('let t=(0,hw.resolve)(e.homeDir??(0,yRe.homedir)())', 'let t=(0,hw.resolve)(e.homeDir??zcodeStandaloneData)'),
        ('l=a?kas(a,t):(0,hw.join)(t,".zcode")', 'l=process.env.ZCODE_STORAGE_DIR'),
    ]
    for old, new in edits:
        text = replace_once(text, old, new)
    return text
