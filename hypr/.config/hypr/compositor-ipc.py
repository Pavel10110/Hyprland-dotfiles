#!/usr/bin/env python3
"""Small provider-aware IPC boundary. Detection is read-only; never try both dialects."""
import argparse, json, re, subprocess

def provider():
    data=json.loads(subprocess.check_output(['hyprctl','-j','version'],text=True))
    # Only the verified 0.56 (hyprlang) and 0.57 (Lua) families are supported.
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?',data.get('version',''))
    if not match: raise RuntimeError('Cannot identify running Hyprland IPC dialect')
    major,minor,_=map(int,match.groups())
    if major != 0 or minor not in (56,57):
        raise RuntimeError('Unvalidated Hyprland version family')
    expected='lua' if minor == 57 else 'hyprlang'
    if 'configProvider' in data and data['configProvider'] != expected:
        raise RuntimeError('Hyprland configProvider contradicts supported version')
    return expected

def lua_string(s):
    # Lua does not accept JSON unicode escapes; encode Unicode literally.
    return json.dumps(s,ensure_ascii=False).replace('\\u0000','\\000')

def command(args,kind):
    q=lua_string
    if args.action=='dpms':
        return ['hyprctl','dispatch',f'hl.dsp.dpms({{action={q(args.state)}}})'] if kind=='lua' else ['hyprctl','dispatch','dpms',args.state]
    if args.action=='move':
        if not re.fullmatch(r'0x[0-9a-fA-F]+',args.address): raise ValueError('Invalid window address')
        return ['hyprctl','dispatch',f'hl.dsp.window.move({{window={q("address:"+args.address)},x={args.x},y={args.y},relative=false}})'] if kind=='lua' else ['hyprctl','dispatch','movewindowpixel',f'exact {args.x} {args.y},address:{args.address}']
    rules={k:getattr(args,k) for k in ('workspace','monitor') if getattr(args,k,None)}
    if kind=='lua':
        table='{'+','.join(k+'='+q(v) for k,v in rules.items())+'}'
        return ['hyprctl','dispatch',f'hl.dsp.exec_cmd({q(args.cmd)}, {table})']
    if any(';' in v or ']' in v or '\n' in v for v in rules.values()): raise ValueError('Unsafe legacy rule value')
    prefix='['+'; '.join(k+' '+v for k,v in rules.items())+'] ' if rules else ''
    return ['hyprctl','dispatch','exec',prefix+args.cmd]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('dpms');p.add_argument('state',choices=['on','off','toggle'])
    p=sub.add_parser('move');p.add_argument('address');p.add_argument('x',type=int);p.add_argument('y',type=int)
    p=sub.add_parser('exec');p.add_argument('--workspace');p.add_argument('--monitor');p.add_argument('cmd')
    args=parser.parse_args()
    try: return subprocess.run(command(args,provider())).returncode
    except (RuntimeError,ValueError,subprocess.CalledProcessError) as e: parser.exit(1,str(e)+'\n')
if __name__=='__main__': raise SystemExit(main())
