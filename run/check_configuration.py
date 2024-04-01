import pathlib
import tomllib
import asyncio
import sys
import json

from pprint import pprint


async def check_networkmanger()->None:
    file = pathlib.Path('/etc/NetworkManager/NetworkManager.conf')
    changed = False
    if file.exists():
        with file.open() as f:
            lines = f.read().split('\n')
        section = False
        has_entry = False
        for idx, line in enumerate(lines):
            if line.startswith('[ifupdown]'):
                section = True
            elif line.startswith('['):
                section = False
            if section and line.startswith('managed'):
                has_entry = True
                if line.startswith('managed=false'):
                    lines[idx] = 'managed=true'
                    changed = True
        if changed:
            with file.open('w') as f:
                f.write('\n'.join(lines))
            p = await asyncio.subprocess.create_subprocess_shell('systemctl restart NetworkManager', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
            await p.wait()

async def check_ip_settings(interface: str, param: dict) -> None:
    p = await asyncio.subprocess.create_subprocess_shell('ip -j address', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    for entry in json.loads(out.decode()):
        if entry['ifname'] == interface:
            for addr in entry['addr_info']:
                if 'inet' == addr['family']:
                    match param.get('method', ''):
                        case 'auto':
                            if not addr.get('dynamic', False):
                                p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device modify {interface} ipv4.method auto;', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                                await p.wait()
                        case 'manual':
                            if not addr.get('dynamic', False):
                                p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device modify {interface} ipv4.method manual;', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                                await p.wait()
                            if ip := param.get('ip'):
                                p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device modify {interface} ipv4.address "{ip}";', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                                await p.wait()
                            if ip := param.get('gateway'):
                                p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device modify {interface} ipv4.gateway "{ip}";', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                                await p.wait()
                            if ip := param.get('dns'):
                                p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device modify {interface} ipv4.dns "{ip}";', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                                await p.wait()
                        case _:
                            print(param.get('method', ''))
                    await asyncio.sleep(2)
                    p = await asyncio.subprocess.create_subprocess_shell(f'nmcli c down {interface}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                    await p.wait()
                    await asyncio.sleep(2)
                    p = await asyncio.subprocess.create_subprocess_shell(f'nmcli c up {interface}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
                    await p.wait()
    
async def check_wifi()->None:
    config_file = pathlib.Path(sys.argv[1]) / 'config' / 'config.toml'
    try:
        with config_file.open('rb') as f:
            cfg = tomllib.load(f)
    except:
        print('Konfiguration nicht geladen')
        return
    has_plugin_data = False
    for p_data in cfg.get('plugins', []):
        if p_data.get('name') == 'network':
            has_plugin_data = True
            data = p_data.get('wifi', {})
    if not has_plugin_data:
        return
    if data.get('default', '') != '':
        p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device wifi show-password', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
        out, _ = await p.communicate()
        ssid = None
        for line in out.decode().split('\n'):
            if line.startswith('SSID:'):
                ssid = line.split(' ')[-1]
        if ssid == data.get('default', ''):
            return #ssid richtig
        password = data.get(data.get("default", ""), '')
        p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device wifi connect {data.get("default", "")} password {password}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
        out, _ = await p.communicate()
    mode_data = p_data.get('mode', {})
    async with asyncio.TaskGroup() as tg:
        for interface, data in mode_data.items():
            tg.create_task(check_ip_settings(interface, data))

async def check_router()->None:
    config_file = pathlib.Path(sys.argv[1]) / 'config' / 'config.toml'
    try:
        with config_file.open('rb') as f:
            cfg = tomllib.load(f)
    except:
        print('Konfiguration nicht geladen')
        return
    has_plugin_data = False
    for p_data in cfg.get('plugins', []):
        if p_data.get('name') == 'network':
            has_plugin_data = True
            data = p_data.get('router', {})
    if not has_plugin_data:
        return
    p = await asyncio.subprocess.create_subprocess_shell(f'mkdir -p /etc/ntftables', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    await p.wait()
    file = pathlib.Path('/etc/ntftables') / f'nft-stat-{data.get("name", "lcars")}.nft'
    with file.open('w') as f:
        f.write('flush ruleset\n\n')
        f.write('table inet ap {\n')
        f.write('  chain routethrough {\n    type nat hook postrouting priority filter; policy accept;\n    oifname "')
        f.write(data.get('dest', ''))
        f.write('" masquerade\n  }\n\n')
        f.write('  chain fward {\n    type filter hook forward priority filter; policy accept;\n    iifname "')
        f.write(data.get('dest', ''))
        f.write('" oifname "')
        f.write(data.get('source', ''))
        f.write('" ct state established,related accept\n    iifname "')
        f.write(data.get('source', ''))
        f.write('" oifname "')
        f.write(data.get('dest', ''))
        f.write('" accept\n  }\n')
        f.write('}\n')
    p = await asyncio.subprocess.create_subprocess_shell(f'chmod +x {str(file)}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    await p.wait()
    file_conf = pathlib.Path('/etc/nftables.conf')
    with file_conf.open() as f:
        lines = f.read().split('\n')
    for line in lines:
        if line.startswith(f'include "{file}"'):
            break
    else:
        lines.append(f'include "{file}"')
        lines.append('')        
    with file_conf.open('w') as f:
        f.write('\n'.join(lines))
    p = await asyncio.subprocess.create_subprocess_shell('systemctl enable nftables ; systemctl restart nftables', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    await p.wait()
    await asyncio.sleep(10)
    p = await asyncio.subprocess.create_subprocess_shell(f"nmcli c up {data.get('source', '')}", 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    await p.wait()

if __name__ == "__main__":
    asyncio.run(check_router())
    asyncio.run(check_networkmanger())
    asyncio.run(check_wifi())
    