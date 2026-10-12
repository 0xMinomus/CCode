"""Local ZCode desktop profile: small tool surface, visual grounding, batched input."""
import json

def install(ns):
    from gi.repository import Gio
    allowed={'screen_screenshot','screen_list_monitors','screen_move_mouse','screen_click','screen_scroll','screen_drag','screen_key','screen_type','screen_do'}
    ns['TOOLS'][:]=[t for t in ns['TOOLS'] if t['name'] in allowed]
    for t in ns['TOOLS']:
        if t['name']=='screen_screenshot':
            t['description']='Observe the real desktop as an image. The vision model reads this image directly; OCR is not required. Start with no args (full desktop). Use the pixel dimensions stated in the returned view header; never guess the scale. Coordinates for clicks are pixels in this latest image: space="view", view_id=<returned id>. Region crops use DESKTOP coordinates, not view pixels; do not crop unless needed.'
        if t['name']=='screen_do':
            t['description']='Execute a predictable sequence in ONE call, then receive a final screenshot by default. steps=[{action:"key",keys:"Ctrl+L"},{action:"type",text:"https://www.youtube.com/"},{action:"key",keys:"Enter"}]. Use after the intended browser is open. Batch only steps whose targets remain known; stop and observe at uncertain navigation. Mouse takeover stops the batch. Never force after STOPPED.'
        if t['name'] in {'screen_click','screen_scroll','screen_drag','screen_key','screen_type','screen_do'}:
            t['description']+=' A post-action screenshot is included by default; inspect it instead of calling screenshot again. Set shot=false only for an intermediate action in a known sequence.'
    # Defaults are enforced in handlers, not merely advertised in JSON Schema.
    for name in ['screen_click','screen_scroll','screen_drag','screen_key','screen_type','screen_do']:
        original=ns['HANDLERS'][name]
        def wrap(args,fn=original):
            args=dict(args);args.setdefault('shot',True);args.setdefault('settle',250)
            return fn(args)
        ns['HANDLERS'][name]=wrap
    def apps(query):
        q=query.casefold().strip();matches=[]
        for app in Gio.AppInfo.get_all():
            if not app.should_show():continue
            name=app.get_display_name() or app.get_name();aid=app.get_id() or ''
            if q==aid.casefold() or q==name.casefold():score=0
            elif q in name.casefold() or q in aid.casefold():score=1
            else:continue
            matches.append((score,aid,name,app))
        return sorted(matches,key=lambda x:(x[0],x[1]))
    def open_app(args):
        query=str(args.get('app','')).strip()
        if not query:return {'content':[ns['_txt']('app is required')],'isError':True}
        rows=apps(query)
        if not rows:return {'content':[ns['_txt']('No installed desktop application matches '+query)],'isError':True}
        best=[r for r in rows if r[0]==rows[0][0]]
        if len(best)>1:
            return {'content':[ns['_txt']('Choose an exact app id from '+json.dumps([{'id':r[1],'name':r[2]} for r in best[:12]]))]}
        row=best[0]
        # Only installed desktop apps; no shell commands, guessed executables, or software-store results.
        ns['inp'].guard_user(False)
        row[3].launch([],None)
        return {'content':[ns['_txt']('Opened '+row[2]+' ('+row[1]+'). Use a screenshot to verify it is ready before input.') ]}
    ns['HANDLERS']['desktop_open_app']=open_app
    ns['TOOLS'].append({'name':'desktop_open_app','title':'Open Desktop App','description':'Open an already-installed real desktop application by name or exact .desktop id. Prefer this over searching the GNOME overview, which may show software-store entries. If ambiguous, returns exact ids without launching. After launch take one screenshot to verify readiness. Does not type or navigate for you.','inputSchema':{'type':'object','properties':{'app':{'type':'string'}},'required':['app']}})
    ns['INSTRUCTIONS']='''Real Linux desktop control via Fedora portal. This IS the configured Computer Use backend.
Use desktop_open_app for installed applications, then screen_screenshot to observe. Images are readable by the vision model without OCR. Do not call OCR/diagnostics to decide whether you can see; inspect the image.
Use screenshot pixel coordinates with space="view" and its view_id. The backend scales to the desktop automatically. Never multiply or divide coordinates yourself. Crops use desktop pixels, so prefer full-screen shots unless small text requires zoom.
Prefer keyboard shortcuts and screen_do for predictable sequences. In a browser, Ctrl+L -> type URL -> Enter is one batch. Receive and inspect the final screenshot. Do not request a second screenshot when the action already returned one. Do not use fixed waits or diagnostics for ordinary navigation. Observe after uncertain transitions and verify the requested result before reporting success.
Mouse takeover/STOPPED means yield to the user. Never set force=true to defeat takeover. Do not repeat a click if it did nothing: observe and choose a different target.'''
