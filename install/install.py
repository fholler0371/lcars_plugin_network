import tomllib
import pathlib
import asyncio
import sys


async def install(parent_cfg: dict) -> dict:
    config_file = pathlib.Path('/'.join(__file__.split('/')[:-2])) / 'config/config.toml'
    cfg = {}
    out = {}
    with config_file.open('rb') as f:
        cfg = tomllib.load(f)
    if 'systemd' in cfg:
        out['systemd'] = []
        for job in cfg['systemd']:
            job['content'] = job['content'].replace('%python%', sys.executable)
            job['content'] = job['content'].replace('%base%', parent_cfg.get('folder', {}).get('base', ''))
            job['content'] = job['content'].replace('%git%', parent_cfg.get('folder', {}).get('base', '')+'/'+parent_cfg.get('folder', {}).get('git', ''))
            out['systemd'].append(job)
    requirements = cfg.get('setup', {}).get('requirements')
    if requirements:
        out['requirements'] = requirements
    run = cfg.get('setup', {}).get('run')
    if run:
        for idx, entry in run.items():
            entry = entry.replace('%base%', parent_cfg.get('folder', {}).get('base', ''))
            run[idx] = entry.replace('%git%', parent_cfg.get('folder', {}).get('git', ''))
        out['run'] = run
    return out
