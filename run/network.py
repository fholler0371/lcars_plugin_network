import sys
if __name__ == '__main__':
    BASE_PATH = sys.argv[1]
    del sys.argv[1]
else:
    BASE_PATH = None
import argparse
import asyncio
import socket
import json

async def print_out(label:str, data:str) -> None:
    print(f'{label :.<30}: {data}')
    
async def hostname(name: str=None) -> str|None:
    if name is None:
        return socket.getfqdn() 
    p = await asyncio.subprocess.create_subprocess_shell(f'sudo hostnamectl set-hostname {name}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    await p.wait()
    
async def interfaces():
    p = await asyncio.subprocess.create_subprocess_shell('ifconfig -s', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    for line in out.decode().split('\n'):
        name = line.split(' ')[0]
        if name not in ['', 'Iface', 'lo'] :
            yield name

async def get_ip4(interface:str)->dict|None:
    p = await asyncio.subprocess.create_subprocess_shell('ip -j address', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    data = json.loads(out.decode())
    result = None
    for entry in data:
        if entry['ifname'] == interface:
            for ip in entry['addr_info']:
                if ip['family'] == 'inet':
                    result = {'ip': ip['local'], 'dhcp': ip.get('dynamic', False)}
    if result is not None:
        p = await asyncio.subprocess.create_subprocess_shell(f'nmcli -p -f general device show {interface} | grep GENERAL.TYPE', 
                                                            stderr=asyncio.subprocess.PIPE, 
                                                            stdout=asyncio.subprocess.PIPE)
        out, _ = await p.communicate()
        result['type'] = out.decode().split(' ')[-1][:-1]
    return result
    
async def get_ssid(interface:str)->str|None:
    p = await asyncio.subprocess.create_subprocess_shell(f'nmcli -p -f wifi-properties device show {interface}', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    if len(out.decode().split('\n')) < 5:
        return None
    p = await asyncio.subprocess.create_subprocess_shell(f'nmcli device wifi show-password', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    for entry in out.decode().split('\n'):
        if entry.startswith('SSID:'):
            return entry.split(' ')[1]
    return None

async def load_config()->None:
    p = await asyncio.subprocess.create_subprocess_shell(f'sudo systemctl start lcars-network', 
                                                         stderr=asyncio.subprocess.PIPE, 
                                                         stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()

async def main() -> None:
    parser = argparse.ArgumentParser(prog='lcars-network',
                                     description='Netzwerktool')
    parser.add_argument('-n', '--hostname', dest='hostname', help='setzt den Hostnamen')
    parser.add_argument('-u', action='store_true', dest='update_config', help='Einstellungen der Konfiguration anwenden')
    args = parser.parse_args()
    if args.hostname is not None:
        await hostname(args.hostname)
    elif args.update_config:
        await load_config()
    else:
        await print_out('Hostname', await hostname())
        print('')
        adapter_info :list = []
        async with asyncio.TaskGroup() as tg:
            async for interface in interfaces():
                adapter_info.append((interface, 'ip4', tg.create_task(get_ip4(interface))))
                adapter_info.append((interface, 'wifi', tg.create_task(get_ssid(interface))))
        adapter = {}
        for entry in adapter_info:
            adapter[entry[0]] = {} if adapter.get(entry[0]) is None else adapter[entry[0]]  
            match entry[1]:
                case 'ip4':
                    adapter[entry[0]]['ip4'] = '---'
                    adapter[entry[0]]['dhcp4'] = False
                    adapter[entry[0]]['type'] = 'unbekannt'
                    if entry[2].result() is not None:
                        adapter[entry[0]]['ip4'] = entry[2].result().get('ip', '---')
                        adapter[entry[0]]['dhcp4'] = entry[2].result().get('dhcp')
                        adapter[entry[0]]['type'] = entry[2].result().get('type')
                case 'wifi':
                    adapter[entry[0]]['ssid'] = entry[2].result()
        for entry, data in adapter.items():
            label = entry
            line = data.get('ip4')
            if data.get('dhcp4', False):
                line += ',dhcp'
            if data.get('ssid') is not None:
                line += f' (ssid: {data["ssid"]})'
            if data.get('type') is not None:
                label += f' ({data["type"]})'
            await print_out(label, line)

if __name__ == '__main__':
    asyncio.run(main())
    
